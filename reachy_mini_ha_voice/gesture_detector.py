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
    THUMBS_UP = "thumbs_up"
    OPEN_PALM = "open_palm"  # Stop gesture


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
        self._on_open_palm: Optional[Callable[[], None]] = None
        
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
        on_open_palm: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set gesture callbacks.
        
        Args:
            on_thumbs_up: Called when thumbs up is detected and held
            on_open_palm: Called when open palm (stop) is detected and held
        """
        self._on_thumbs_up = on_thumbs_up
        self._on_open_palm = on_open_palm

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
        thumb_tip = self._get_landmark_coords(hand_landmarks, 4)
        thumb_ip = self._get_landmark_coords(hand_landmarks, 3)
        thumb_mcp = self._get_landmark_coords(hand_landmarks, 2)
        
        index_tip = self._get_landmark_coords(hand_landmarks, 8)
        index_mcp = self._get_landmark_coords(hand_landmarks, 5)
        
        middle_tip = self._get_landmark_coords(hand_landmarks, 12)
        middle_mcp = self._get_landmark_coords(hand_landmarks, 9)
        
        ring_tip = self._get_landmark_coords(hand_landmarks, 16)
        ring_mcp = self._get_landmark_coords(hand_landmarks, 13)
        
        pinky_tip = self._get_landmark_coords(hand_landmarks, 20)
        pinky_mcp = self._get_landmark_coords(hand_landmarks, 17)
        
        # Check if fingers are extended (tip above MCP in y)
        # Note: y increases downward in image coordinates
        index_extended = index_tip[1] < index_mcp[1]
        middle_extended = middle_tip[1] < middle_mcp[1]
        ring_extended = ring_tip[1] < ring_mcp[1]
        pinky_extended = pinky_tip[1] < pinky_mcp[1]
        
        # Thumb is extended if tip is far from index MCP (horizontally)
        thumb_extended = abs(thumb_tip[0] - index_mcp[0]) > 0.1
        
        # Thumbs up: thumb extended upward, other fingers closed
        # Thumb tip should be above thumb MCP (pointing up)
        thumb_pointing_up = thumb_tip[1] < thumb_mcp[1]
        fingers_closed = not (index_extended or middle_extended or ring_extended or pinky_extended)
        
        if thumb_pointing_up and thumb_extended and fingers_closed:
            return Gesture.THUMBS_UP
        
        # Open palm (stop): all fingers extended
        all_extended = index_extended and middle_extended and ring_extended and pinky_extended
        if all_extended:
            return Gesture.OPEN_PALM
        
        return Gesture.NONE

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
                
                if current_gesture == Gesture.THUMBS_UP and self._on_thumbs_up:
                    logger.info("Gesture triggered: THUMBS_UP")
                    try:
                        self._on_thumbs_up()
                    except Exception as e:
                        logger.error("Thumbs up callback error: %s", e)
                    return Gesture.THUMBS_UP
                    
                elif current_gesture == Gesture.OPEN_PALM and self._on_open_palm:
                    logger.info("Gesture triggered: OPEN_PALM (stop)")
                    try:
                        self._on_open_palm()
                    except Exception as e:
                        logger.error("Open palm callback error: %s", e)
                    return Gesture.OPEN_PALM
        
        return None

    def close(self) -> None:
        """Release resources."""
        if self._hands is not None:
            self._hands.close()
            self._hands = None
