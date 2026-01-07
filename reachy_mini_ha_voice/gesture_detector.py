"""Gesture detection using MediaPipe Hands.

Detects 11 hand gestures for robot interaction:
- thumbs_up: 👍 Confirmation/like
- thumbs_down: 👎 Reject/dislike  
- open_palm: ✋ Stop/halt
- fist: ✊ Pause/hold
- peace: ✌️ Victory sign
- pointing_up: ☝️ Attention/one
- ok: 👌 OK sign
- rock: 🤘 Rock on
- call: 🤙 Call me
- three: 3️⃣ Three fingers
- four: 4️⃣ Four fingers

Requires mediapipe to be pre-installed. If not available, gesture detection
is silently disabled (no network installation attempts).

For ARM64 (Raspberry Pi), install manually:
    pip install mediapipe==0.10.18 --no-deps
    pip install flatbuffers absl-py
"""

from __future__ import annotations
import logging
from enum import Enum
from typing import Optional, Tuple, Callable
import time

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


# Try to import mediapipe (no auto-install to avoid network issues)
_mp_hands = None
_mediapipe_available = False

try:
    import mediapipe as mp
    _mp_hands = mp.solutions.hands
    _mediapipe_available = True
    logger.info("MediaPipe loaded for gesture detection")
except ImportError:
    logger.info("MediaPipe not installed - gesture detection disabled")
except Exception as e:
    logger.warning("MediaPipe load error: %s - gesture detection disabled", e)


class Gesture(Enum):
    """Recognized gestures."""
    NONE = "none"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    OPEN_PALM = "open_palm"
    FIST = "fist"
    PEACE = "peace"
    POINTING_UP = "pointing_up"
    OK = "ok"
    ROCK = "rock"
    CALL = "call"
    THREE = "three"
    FOUR = "four"


class GestureDetector:
    """Gesture detector using MediaPipe Hands."""

    def __init__(
        self,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.5,
        max_num_hands: int = 1,
    ) -> None:
        self._hands = None
        self._available = False
        
        # Callbacks
        self._callbacks: dict[Gesture, Optional[Callable[[], None]]] = {
            g: None for g in Gesture if g != Gesture.NONE
        }
        
        # State
        self._last_gesture = Gesture.NONE
        self._current_gesture = Gesture.NONE
        self._gesture_start_time: Optional[float] = None
        self._gesture_hold_threshold = 0.5
        self._gesture_cooldown = 1.5
        self._last_trigger_time: float = 0
        self._gesture_clear_delay = 2.0
        self._last_gesture_time: float = 0
        
        if _mediapipe_available and _mp_hands is not None:
            try:
                self._hands = _mp_hands.Hands(
                    static_image_mode=False,
                    max_num_hands=max_num_hands,
                    min_detection_confidence=min_detection_confidence,
                    min_tracking_confidence=min_tracking_confidence,
                )
                self._available = True
                logger.info("MediaPipe Hands initialized")
            except Exception as e:
                logger.warning("Failed to initialize MediaPipe Hands: %s", e)

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
        on_rock: Optional[Callable[[], None]] = None,
        on_call: Optional[Callable[[], None]] = None,
        on_three: Optional[Callable[[], None]] = None,
        on_four: Optional[Callable[[], None]] = None,
    ) -> None:
        self._callbacks[Gesture.THUMBS_UP] = on_thumbs_up
        self._callbacks[Gesture.THUMBS_DOWN] = on_thumbs_down
        self._callbacks[Gesture.OPEN_PALM] = on_open_palm
        self._callbacks[Gesture.FIST] = on_fist
        self._callbacks[Gesture.PEACE] = on_peace
        self._callbacks[Gesture.OK] = on_ok
        self._callbacks[Gesture.POINTING_UP] = on_pointing_up
        self._callbacks[Gesture.ROCK] = on_rock
        self._callbacks[Gesture.CALL] = on_call
        self._callbacks[Gesture.THREE] = on_three
        self._callbacks[Gesture.FOUR] = on_four

    def _lm(self, landmarks, idx: int) -> Tuple[float, float, float]:
        lm = landmarks.landmark[idx]
        return lm.x, lm.y, lm.z

    def _dist(self, p1: Tuple[float, ...], p2: Tuple[float, ...]) -> float:
        return sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5

    def _is_extended(self, landmarks, tip: int, pip: int) -> bool:
        return self._lm(landmarks, tip)[1] < self._lm(landmarks, pip)[1]

    def _classify_gesture(self, landmarks) -> Gesture:
        thumb_tip = self._lm(landmarks, 4)
        thumb_mcp = self._lm(landmarks, 2)
        index_tip = self._lm(landmarks, 8)
        index_mcp = self._lm(landmarks, 5)
        
        index_ext = self._is_extended(landmarks, 8, 6)
        middle_ext = self._is_extended(landmarks, 12, 10)
        ring_ext = self._is_extended(landmarks, 16, 14)
        pinky_ext = self._is_extended(landmarks, 20, 18)
        
        thumb_extended = abs(thumb_tip[0] - index_mcp[0]) > 0.1
        thumb_up = thumb_tip[1] < thumb_mcp[1] - 0.08
        thumb_down = thumb_tip[1] > thumb_mcp[1] + 0.08
        
        ext_count = sum([index_ext, middle_ext, ring_ext, pinky_ext])
        all_curled = ext_count == 0
        
        thumb_index_dist = self._dist(thumb_tip, index_tip)
        
        # Thumbs up
        if thumb_up and thumb_extended and all_curled:
            return Gesture.THUMBS_UP
        
        # Thumbs down
        if thumb_down and thumb_extended and all_curled:
            return Gesture.THUMBS_DOWN
        
        # Fist
        if all_curled and not thumb_extended:
            return Gesture.FIST
        
        # OK sign
        if thumb_index_dist < 0.05 and middle_ext and ring_ext and pinky_ext:
            return Gesture.OK
        
        # Rock (index + pinky)
        if index_ext and pinky_ext and not middle_ext and not ring_ext:
            return Gesture.ROCK
        
        # Call (thumb + pinky)
        if thumb_extended and pinky_ext and not index_ext and not middle_ext and not ring_ext:
            return Gesture.CALL
        
        # Pointing up
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return Gesture.POINTING_UP
        
        # Peace
        if index_ext and middle_ext and not ring_ext and not pinky_ext:
            return Gesture.PEACE
        
        # Three
        if index_ext and middle_ext and ring_ext and not pinky_ext:
            return Gesture.THREE
        
        # Four
        if index_ext and middle_ext and ring_ext and pinky_ext and not thumb_extended:
            return Gesture.FOUR
        
        # Open palm
        if ext_count >= 4 and thumb_extended:
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
        
        if gesture != Gesture.NONE:
            self._current_gesture = gesture
            self._last_gesture_time = now
        elif now - self._last_gesture_time > self._gesture_clear_delay:
            self._current_gesture = Gesture.NONE
        
        if now - self._last_trigger_time < self._gesture_cooldown:
            return None
        
        if gesture != self._last_gesture:
            self._last_gesture = gesture
            self._gesture_start_time = now if gesture != Gesture.NONE else None
            return None
        
        if gesture != Gesture.NONE and self._gesture_start_time:
            if now - self._gesture_start_time >= self._gesture_hold_threshold:
                self._last_trigger_time = now
                self._gesture_start_time = None
                
                callback = self._callbacks.get(gesture)
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
