"""Gesture detection using MediaPipe Hands.

Detects hand gestures for robot interaction:
- Thumbs up: Confirmation/like
- Open palm (stop): Stop speaking/cancel

Uses MediaPipe which is lightweight and can run alongside YOLO face detection.
"""

from __future__ import annotations
import logging
from enum import Enum
from typing import Optional, Tuple, Callable, List
import threading
import time

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class Gesture(Enum):
    """Recognized gestures."""
    NONE = "none"
    THUMBS_UP = "thumbs_up"      # 👍 Confirm/like
    THUMBS_DOWN = "thumbs_down"  # 👎 Reject/dislike
    OPEN_PALM = "open_palm"      # ✋ Stop
    FIST = "fist"                # ✊ Pause/hold
    PEACE = "peace"              # ✌️ Victory/peace sign
    OK = "ok"                    # 👌 OK sign
    POINTING_UP = "pointing_up"  # ☝️ Attention/one
    WAVE = "wave"                # 👋 Hello/goodbye (open palm moving)


class GestureDetector:
    """Lightweight gesture detector using MediaPipe Hands.
    
    Designed to run alongside YOLO face detection with minimal overhead.
    """

    def __init__(
        self,
        min_detection_confidence: float = 0.6,
        min_tracking_confidence: float = 0.5,
        max_num_hands: int = 1,
    ) -> None:
        """Initialize gesture detector.

        Args:
            min_detection_confidence: Minimum confidence for hand detection
            min_tracking_confidence: Minimum confidence for hand tracking
            max_num_hands: Maximum number of hands to detect (1 is faster)
        """
        self._min_detection_confidence = min_detection_confidence
        self._min_tracking_confidence = min_tracking_confidence
        self._max_num_hands = max_num_hands
        
        self._hands = None
        self._mp_hands = None
        self._load_attempted = False
        self._load_error: Optional[str] = None
        
        # Gesture callbacks
        self._on_thumbs_up: Optional[Callable[[], None]] = None
        self._on_thumbs_down: Optional[Callable[[], None]] = None
        self._on_open_palm: Optional[Callable[[], None]] = None
        self._on_fist: Optional[Callable[[], None]] = None
        self._on_peace: Optional[Callable[[], None]] = None
        self._on_ok: Optional[Callable[[], None]] = None
        self._on_pointing_up: Optional[Callable[[], None]] = None
        
        # Gesture state (for debouncing)
        self._last_gesture = Gesture.NONE
        self._current_gesture = Gesture.NONE  # Currently active gesture (for HA entity)
        self._gesture_start_time: Optional[float] = None
        self._gesture_hold_threshold = 0.5  # Hold gesture for 0.5s to trigger
        self._gesture_cooldown = 1.5  # Cooldown between triggers
        self._last_trigger_time: float = 0
        self._gesture_clear_delay = 2.0  # Clear gesture after 2s of no detection
        self._last_gesture_time: float = 0
        
        # Load model
        self._load_model()

    def _load_model(self) -> None:
        """Load MediaPipe Hands model."""
        if self._load_attempted:
            return
        
        self._load_attempted = True
        
        try:
            import mediapipe as mp
            
            self._mp_hands = mp.solutions.hands
            self._hands = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=self._max_num_hands,
                min_detection_confidence=self._min_detection_confidence,
                min_tracking_confidence=self._min_tracking_confidence,
            )
            logger.info("MediaPipe Hands loaded for gesture detection")
        except ImportError as e:
            self._load_error = f"Missing mediapipe: {e}"
            logger.warning(
                "Gesture detection disabled - missing mediapipe. "
                "Install with: pip install mediapipe"
            )
        except Exception as e:
            self._load_error = str(e)
            logger.error("Failed to load MediaPipe Hands: %s", e)

    @property
    def is_available(self) -> bool:
        """Check if gesture detector is available."""
        return self._hands is not None

    @property
    def current_gesture(self) -> Gesture:
        """Get current detected gesture (for HA entity)."""
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
        """Set gesture callbacks.
        
        Args:
            on_thumbs_up: Called when thumbs up is detected (confirm/like)
            on_thumbs_down: Called when thumbs down is detected (reject)
            on_open_palm: Called when open palm is detected (stop)
            on_fist: Called when fist is detected (pause)
            on_peace: Called when peace sign is detected
            on_ok: Called when OK sign is detected
            on_pointing_up: Called when pointing up is detected
        """
        self._on_thumbs_up = on_thumbs_up
        self._on_thumbs_down = on_thumbs_down
        self._on_open_palm = on_open_palm
        self._on_fist = on_fist
        self._on_peace = on_peace
        self._on_ok = on_ok
        self._on_pointing_up = on_pointing_up

    def _get_landmark_coords(
        self, landmarks, idx: int
    ) -> Tuple[float, float, float]:
        """Get x, y, z coordinates for a landmark."""
        lm = landmarks.landmark[idx]
        return lm.x, lm.y, lm.z

    def _classify_gesture(self, hand_landmarks) -> Gesture:
        """Classify hand gesture from landmarks.
        
        Landmark indices (MediaPipe):
        - 0: Wrist
        - 4: Thumb tip
        - 8: Index finger tip
        - 12: Middle finger tip
        - 16: Ring finger tip
        - 20: Pinky tip
        - 2, 3: Thumb joints
        - 5, 6, 7: Index joints
        - etc.
        """
        # Get key landmarks
        wrist = self._get_landmark_coords(hand_landmarks, 0)
        
        # Thumb landmarks
        thumb_tip = self._get_landmark_coords(hand_landmarks, 4)
        thumb_ip = self._get_landmark_coords(hand_landmarks, 3)
        thumb_mcp = self._get_landmark_coords(hand_landmarks, 2)
        thumb_cmc = self._get_landmark_coords(hand_landmarks, 1)
        
        # Index finger landmarks
        index_tip = self._get_landmark_coords(hand_landmarks, 8)
        index_dip = self._get_landmark_coords(hand_landmarks, 7)
        index_pip = self._get_landmark_coords(hand_landmarks, 6)
        index_mcp = self._get_landmark_coords(hand_landmarks, 5)
        
        # Middle finger landmarks
        middle_tip = self._get_landmark_coords(hand_landmarks, 12)
        middle_dip = self._get_landmark_coords(hand_landmarks, 11)
        middle_pip = self._get_landmark_coords(hand_landmarks, 10)
        middle_mcp = self._get_landmark_coords(hand_landmarks, 9)
        
        # Ring finger landmarks
        ring_tip = self._get_landmark_coords(hand_landmarks, 16)
        ring_dip = self._get_landmark_coords(hand_landmarks, 15)
        ring_pip = self._get_landmark_coords(hand_landmarks, 14)
        ring_mcp = self._get_landmark_coords(hand_landmarks, 13)
        
        # Pinky landmarks
        pinky_tip = self._get_landmark_coords(hand_landmarks, 20)
        pinky_dip = self._get_landmark_coords(hand_landmarks, 19)
        pinky_pip = self._get_landmark_coords(hand_landmarks, 18)
        pinky_mcp = self._get_landmark_coords(hand_landmarks, 17)
        
        # Check if fingers are extended (tip above PIP in y, y increases downward)
        index_extended = index_tip[1] < index_pip[1]
        middle_extended = middle_tip[1] < middle_pip[1]
        ring_extended = ring_tip[1] < ring_pip[1]
        pinky_extended = pinky_tip[1] < pinky_pip[1]
        
        # Thumb extended check (horizontal distance from palm)
        thumb_extended = abs(thumb_tip[0] - index_mcp[0]) > 0.08
        
        # Thumb pointing direction
        thumb_pointing_up = thumb_tip[1] < thumb_mcp[1] - 0.05
        thumb_pointing_down = thumb_tip[1] > thumb_mcp[1] + 0.05
        
        # Count extended fingers (excluding thumb)
        extended_count = sum([index_extended, middle_extended, ring_extended, pinky_extended])
        
        # Fingers curled (tip below MCP)
        index_curled = index_tip[1] > index_mcp[1]
        middle_curled = middle_tip[1] > middle_mcp[1]
        ring_curled = ring_tip[1] > ring_mcp[1]
        pinky_curled = pinky_tip[1] > pinky_mcp[1]
        all_fingers_curled = index_curled and middle_curled and ring_curled and pinky_curled
        
        # ===== Gesture Classification =====
        
        # 👍 Thumbs up: thumb pointing up, all other fingers curled
        if thumb_pointing_up and thumb_extended and all_fingers_curled:
            return Gesture.THUMBS_UP
        
        # 👎 Thumbs down: thumb pointing down, all other fingers curled
        if thumb_pointing_down and thumb_extended and all_fingers_curled:
            return Gesture.THUMBS_DOWN
        
        # ✊ Fist: all fingers curled including thumb tucked
        if all_fingers_curled and not thumb_extended:
            return Gesture.FIST
        
        # ✌️ Peace: index and middle extended, others curled
        if index_extended and middle_extended and not ring_extended and not pinky_extended:
            return Gesture.PEACE
        
        # ☝️ Pointing up: only index extended
        if index_extended and not middle_extended and not ring_extended and not pinky_extended:
            return Gesture.POINTING_UP
        
        # 👌 OK sign: thumb and index tips close together, other fingers extended
        thumb_index_distance = self._distance(thumb_tip, index_tip)
        if thumb_index_distance < 0.05 and middle_extended and ring_extended and pinky_extended:
            return Gesture.OK
        
        # ✋ Open palm: all fingers extended
        if extended_count >= 4:
            return Gesture.OPEN_PALM
        
        return Gesture.NONE
    
    def _distance(self, p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
        """Calculate Euclidean distance between two points."""
        return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2 + (p1[2] - p2[2])**2) ** 0.5

    def detect(self, frame: NDArray[np.uint8]) -> Gesture:
        """Detect gesture in frame.
        
        Args:
            frame: BGR image from camera
            
        Returns:
            Detected gesture (may be NONE)
        """
        if not self.is_available:
            return Gesture.NONE
        
        try:
            import cv2
            
            # Convert BGR to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process frame
            results = self._hands.process(rgb_frame)
            
            if not results.multi_hand_landmarks:
                return Gesture.NONE
            
            # Use first detected hand
            hand_landmarks = results.multi_hand_landmarks[0]
            gesture = self._classify_gesture(hand_landmarks)
            
            return gesture
            
        except Exception as e:
            logger.debug("Gesture detection error: %s", e)
            return Gesture.NONE

    def process_frame(self, frame: NDArray[np.uint8]) -> Optional[Gesture]:
        """Process frame and trigger callbacks if gesture held.
        
        This method handles debouncing and cooldown logic.
        
        Args:
            frame: BGR image from camera
            
        Returns:
            Triggered gesture or None
        """
        current_gesture = self.detect(frame)
        current_time = time.time()
        
        # Update current gesture for HA entity
        if current_gesture != Gesture.NONE:
            self._current_gesture = current_gesture
            self._last_gesture_time = current_time
        elif current_time - self._last_gesture_time > self._gesture_clear_delay:
            # Clear gesture after delay
            self._current_gesture = Gesture.NONE
        
        # Check cooldown
        if current_time - self._last_trigger_time < self._gesture_cooldown:
            return None
        
        # Gesture changed
        if current_gesture != self._last_gesture:
            self._last_gesture = current_gesture
            self._gesture_start_time = current_time if current_gesture != Gesture.NONE else None
            return None
        
        # Same gesture - check if held long enough
        if current_gesture != Gesture.NONE and self._gesture_start_time is not None:
            hold_duration = current_time - self._gesture_start_time
            
            if hold_duration >= self._gesture_hold_threshold:
                # Trigger callback
                self._last_trigger_time = current_time
                self._gesture_start_time = None  # Reset to prevent re-trigger
                
                # Get callback for this gesture
                callback = self._get_callback_for_gesture(current_gesture)
                if callback:
                    logger.info("Gesture triggered: %s", current_gesture.value)
                    try:
                        callback()
                    except Exception as e:
                        logger.error("Gesture callback error (%s): %s", current_gesture.value, e)
                    return current_gesture
        
        return None
    
    def _get_callback_for_gesture(self, gesture: Gesture) -> Optional[Callable[[], None]]:
        """Get the callback function for a gesture."""
        callbacks = {
            Gesture.THUMBS_UP: self._on_thumbs_up,
            Gesture.THUMBS_DOWN: self._on_thumbs_down,
            Gesture.OPEN_PALM: self._on_open_palm,
            Gesture.FIST: self._on_fist,
            Gesture.PEACE: self._on_peace,
            Gesture.OK: self._on_ok,
            Gesture.POINTING_UP: self._on_pointing_up,
        }
        return callbacks.get(gesture)

    def close(self) -> None:
        """Release resources."""
        if self._hands is not None:
            self._hands.close()
            self._hands = None
