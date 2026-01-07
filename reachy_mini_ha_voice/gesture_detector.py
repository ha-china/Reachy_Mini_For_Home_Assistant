"""Gesture detection using MediaPipe Hands.

Detects hand gestures for robot interaction:
- thumbs_up: Confirmation/like
- thumbs_down: Reject/dislike  
- open_palm: Stop speaking/cancel
- fist: Pause/hold
- peace: Victory sign (2 fingers)
- pointing_up: Attention (1 finger)
"""

from __future__ import annotations
import logging
from enum import Enum
from typing import Optional, Tuple, Callable
import time

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class Gesture(Enum):
    """Recognized gestures."""
    NONE = "none"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    OPEN_PALM = "open_palm"
    FIST = "fist"
    PEACE = "peace"
    POINTING_UP = "pointing_up"


class GestureDetector:
    """Gesture detector using MediaPipe Hands."""

    def __init__(
        self,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.5,
        max_num_hands: int = 1,
    ) -> None:
        self._min_detection_confidence = min_detection_confidence
        self._min_tracking_confidence = min_tracking_confidence
        self._max_num_hands = max_num_hands
        
        self._hands = None
        self._mp_hands = None
        self._available = False
        
        # Callbacks
        self._on_thumbs_up: Optional[Callable[[], None]] = None
        self._on_thumbs_down: Optional[Callable[[], None]] = None
        self._on_open_palm: Optional[Callable[[], None]] = None
        self._on_fist: Optional[Callable[[], None]] = None
        self._on_peace: Optional[Callable[[], None]] = None
        self._on_pointing_up: Optional[Callable[[], None]] = None
        
        # State
        self._last_gesture = Gesture.NONE
        self._current_gesture = Gesture.NONE
        self._gesture_start_time: Optional[float] = None
        self._gesture_hold_threshold = 0.5
        self._gesture_cooldown = 1.5
        self._last_trigger_time: float = 0
        self._gesture_clear_delay = 2.0
        self._last_gesture_time: float = 0
        
        self._load_model()

    def _load_model(self) -> None:
        try:
            import mediapipe as mp
            self._mp_hands = mp.solutions.hands
            self._hands = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=self._max_num_hands,
                min_detection_confidence=self._min_detection_confidence,
                min_tracking_confidence=self._min_tracking_confidence,
            )
            self._available = True
            logger.info("MediaPipe Hands loaded for gesture detection")
        except ImportError as e:
            logger.warning("Gesture detection disabled - mediapipe not installed: %s", e)
        except Exception as e:
            logger.error("Failed to load MediaPipe Hands: %s", e)

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def current_gesture(self) -> Gesture:
        return self._current_gesture

    def set_callbacks(
        self,
        on_thumbs_up: Optional[Callable[[], None]] = None,
        on_thumbs_down: Optional[Callable[[], None]] = None,
        on_open_palm: Optional[Callable[[], None]] = None,
        on_fist: Optional[Callable[[], None]] = None,
        on_peace: Optional[Callable[[], None]] = None,
        on_ok: Optional[Callable[[], None]] = None,
        on_pointing_up: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_thumbs_up = on_thumbs_up
        self._on_thumbs_down = on_thumbs_down
        self._on_open_palm = on_open_palm
        self._on_fist = on_fist
        self._on_peace = on_peace
        self._on_pointing_up = on_pointing_up

    def _get_landmark(self, landmarks, idx: int) -> Tuple[float, float, float]:
        lm = landmarks.landmark[idx]
        return lm.x, lm.y, lm.z

    def _is_finger_extended(self, landmarks, tip_idx: int, pip_idx: int) -> bool:
        """Check if finger is extended (tip above PIP joint)."""
        tip = self._get_landmark(landmarks, tip_idx)
        pip = self._get_landmark(landmarks, pip_idx)
        return tip[1] < pip[1]  # y increases downward

    def _classify_gesture(self, landmarks) -> Gesture:
        # Finger tip and PIP indices
        # Thumb: 4 (tip), 3 (IP), 2 (MCP)
        # Index: 8 (tip), 6 (PIP)
        # Middle: 12 (tip), 10 (PIP)
        # Ring: 16 (tip), 14 (PIP)
        # Pinky: 20 (tip), 18 (PIP)
        
        thumb_tip = self._get_landmark(landmarks, 4)
        thumb_ip = self._get_landmark(landmarks, 3)
        thumb_mcp = self._get_landmark(landmarks, 2)
        index_mcp = self._get_landmark(landmarks, 5)
        wrist = self._get_landmark(landmarks, 0)
        
        # Check finger extension
        index_ext = self._is_finger_extended(landmarks, 8, 6)
        middle_ext = self._is_finger_extended(landmarks, 12, 10)
        ring_ext = self._is_finger_extended(landmarks, 16, 14)
        pinky_ext = self._is_finger_extended(landmarks, 20, 18)
        
        # Thumb extended (horizontal distance from palm)
        thumb_extended = abs(thumb_tip[0] - index_mcp[0]) > 0.1
        
        # Thumb direction
        thumb_up = thumb_tip[1] < thumb_mcp[1] - 0.08
        thumb_down = thumb_tip[1] > thumb_mcp[1] + 0.08
        
        # Count extended fingers (excluding thumb)
        ext_count = sum([index_ext, middle_ext, ring_ext, pinky_ext])
        
        # All fingers curled
        all_curled = not index_ext and not middle_ext and not ring_ext and not pinky_ext
        
        # Thumbs up: thumb up, all others curled
        if thumb_up and thumb_extended and all_curled:
            return Gesture.THUMBS_UP
        
        # Thumbs down: thumb down, all others curled
        if thumb_down and thumb_extended and all_curled:
            return Gesture.THUMBS_DOWN
        
        # Fist: all fingers curled, thumb tucked
        if all_curled and not thumb_extended:
            return Gesture.FIST
        
        # Peace: index and middle extended, others curled
        if index_ext and middle_ext and not ring_ext and not pinky_ext:
            return Gesture.PEACE
        
        # Pointing up: only index extended
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return Gesture.POINTING_UP
        
        # Open palm: 4+ fingers extended
        if ext_count >= 4:
            return Gesture.OPEN_PALM
        
        return Gesture.NONE

    def detect(self, frame: NDArray[np.uint8]) -> Gesture:
        if not self._available:
            return Gesture.NONE
        
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)
            
            if not results.multi_hand_landmarks:
                return Gesture.NONE
            
            return self._classify_gesture(results.multi_hand_landmarks[0])
        except Exception as e:
            logger.debug("Gesture detection error: %s", e)
            return Gesture.NONE

    def process_frame(self, frame: NDArray[np.uint8]) -> Optional[Gesture]:
        gesture = self.detect(frame)
        now = time.time()
        
        # Update current gesture for HA entity
        if gesture != Gesture.NONE:
            self._current_gesture = gesture
            self._last_gesture_time = now
        elif now - self._last_gesture_time > self._gesture_clear_delay:
            self._current_gesture = Gesture.NONE
        
        # Cooldown check
        if now - self._last_trigger_time < self._gesture_cooldown:
            return None
        
        # Gesture changed
        if gesture != self._last_gesture:
            self._last_gesture = gesture
            self._gesture_start_time = now if gesture != Gesture.NONE else None
            return None
        
        # Same gesture held long enough
        if gesture != Gesture.NONE and self._gesture_start_time:
            if now - self._gesture_start_time >= self._gesture_hold_threshold:
                self._last_trigger_time = now
                self._gesture_start_time = None
                
                callback = {
                    Gesture.THUMBS_UP: self._on_thumbs_up,
                    Gesture.THUMBS_DOWN: self._on_thumbs_down,
                    Gesture.OPEN_PALM: self._on_open_palm,
                    Gesture.FIST: self._on_fist,
                    Gesture.PEACE: self._on_peace,
                    Gesture.POINTING_UP: self._on_pointing_up,
                }.get(gesture)
                
                if callback:
                    logger.info("Gesture triggered: %s", gesture.value)
                    try:
                        callback()
                    except Exception as e:
                        logger.error("Gesture callback error: %s", e)
                    return gesture
        
        return None

    def close(self) -> None:
        if self._hands:
            self._hands.close()
            self._hands = None
