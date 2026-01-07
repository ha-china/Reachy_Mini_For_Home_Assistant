"""Gesture detection using OpenCV skin color detection and contour analysis.

Detects hand gestures for robot interaction:
- thumbs_up: Confirmation/like
- thumbs_down: Reject/dislike  
- open_palm: Stop speaking/cancel (5 fingers)
- fist: Pause/hold (0 fingers)
- peace: Victory sign (2 fingers)
- pointing_up: Attention (1 finger)

Uses pure OpenCV - no additional dependencies required.
"""

from __future__ import annotations
import logging
from enum import Enum
from typing import Optional, Tuple, Callable
import time

import cv2
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
    """Gesture detector using OpenCV skin detection and convex hull analysis."""

    def __init__(
        self,
        min_hand_area: int = 5000,
        max_hand_area: int = 150000,
    ) -> None:
        """Initialize gesture detector.

        Args:
            min_hand_area: Minimum contour area to consider as hand
            max_hand_area: Maximum contour area to consider as hand
        """
        self._min_hand_area = min_hand_area
        self._max_hand_area = max_hand_area
        
        # Gesture callbacks
        self._on_thumbs_up: Optional[Callable[[], None]] = None
        self._on_thumbs_down: Optional[Callable[[], None]] = None
        self._on_open_palm: Optional[Callable[[], None]] = None
        self._on_fist: Optional[Callable[[], None]] = None
        self._on_peace: Optional[Callable[[], None]] = None
        self._on_pointing_up: Optional[Callable[[], None]] = None
        
        # Gesture state
        self._last_gesture = Gesture.NONE
        self._current_gesture = Gesture.NONE
        self._gesture_start_time: Optional[float] = None
        self._gesture_hold_threshold = 0.5
        self._gesture_cooldown = 1.5
        self._last_trigger_time: float = 0
        self._gesture_clear_delay = 2.0
        self._last_gesture_time: float = 0
        
        logger.info("OpenCV gesture detector initialized")

    @property
    def is_available(self) -> bool:
        """Always available - uses OpenCV only."""
        return True

    @property
    def current_gesture(self) -> Gesture:
        """Get current detected gesture."""
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
        """Set gesture callbacks."""
        self._on_thumbs_up = on_thumbs_up
        self._on_thumbs_down = on_thumbs_down
        self._on_open_palm = on_open_palm
        self._on_fist = on_fist
        self._on_peace = on_peace
        self._on_pointing_up = on_pointing_up

    def _detect_skin(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Detect skin regions using YCrCb color space."""
        # Convert to YCrCb
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        
        # Skin color range in YCrCb
        lower = np.array([0, 133, 77], dtype=np.uint8)
        upper = np.array([255, 173, 127], dtype=np.uint8)
        
        # Create mask
        mask = cv2.inRange(ycrcb, lower, upper)
        
        # Morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        
        return mask

    def _find_hand_contour(self, mask: NDArray[np.uint8]) -> Optional[NDArray]:
        """Find the largest hand contour in the mask."""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Find largest contour within size bounds
        valid_contours = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self._min_hand_area < area < self._max_hand_area:
                valid_contours.append((area, cnt))
        
        if not valid_contours:
            return None
        
        # Return largest valid contour
        valid_contours.sort(key=lambda x: x[0], reverse=True)
        return valid_contours[0][1]

    def _count_fingers(self, contour: NDArray, frame_height: int) -> Tuple[int, bool, float]:
        """Count extended fingers using convex hull defects.
        
        Returns:
            Tuple of (finger_count, is_thumb_extended, hand_center_y_ratio)
        """
        # Get convex hull
        hull = cv2.convexHull(contour, returnPoints=False)
        
        if len(hull) < 3:
            return 0, False, 0.5
        
        # Get convex hull points for centroid
        hull_points = cv2.convexHull(contour)
        
        # Calculate centroid
        M = cv2.moments(contour)
        if M["m00"] == 0:
            return 0, False, 0.5
        
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        center_y_ratio = cy / frame_height
        
        # Get bounding rect for reference
        x, y, w, h = cv2.boundingRect(contour)
        
        # Get convexity defects
        try:
            defects = cv2.convexityDefects(contour, hull)
        except cv2.error:
            return 0, False, center_y_ratio
        
        if defects is None:
            return 0, False, center_y_ratio
        
        # Count fingers based on defects
        finger_count = 0
        thumb_extended = False
        
        for i in range(defects.shape[0]):
            s, e, f, d = defects[i, 0]
            start = tuple(contour[s][0])
            end = tuple(contour[e][0])
            far = tuple(contour[f][0])
            
            # Calculate distances
            a = np.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
            b = np.sqrt((far[0] - start[0])**2 + (far[1] - start[1])**2)
            c = np.sqrt((end[0] - far[0])**2 + (end[1] - far[1])**2)
            
            # Calculate angle using cosine rule
            if b * c == 0:
                continue
            angle = np.arccos((b**2 + c**2 - a**2) / (2 * b * c))
            
            # Finger detected if angle < 90 degrees and defect depth is significant
            if angle <= np.pi / 2 and d > 10000:
                finger_count += 1
                
                # Check if this might be thumb (on side of hand)
                if abs(start[0] - cx) > w * 0.3 or abs(end[0] - cx) > w * 0.3:
                    thumb_extended = True
        
        # Add 1 because defects count spaces between fingers
        if finger_count > 0:
            finger_count += 1
        
        return min(finger_count, 5), thumb_extended, center_y_ratio

    def _classify_gesture(self, contour: NDArray, frame_height: int) -> Gesture:
        """Classify gesture based on contour analysis."""
        finger_count, thumb_extended, center_y = self._count_fingers(contour, frame_height)
        
        # Get contour properties
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = float(w) / h if h > 0 else 1.0
        
        # Get hull area ratio (solidity)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        contour_area = cv2.contourArea(contour)
        solidity = contour_area / hull_area if hull_area > 0 else 0
        
        # Classify based on finger count and shape
        if finger_count >= 4:
            return Gesture.OPEN_PALM
        elif finger_count == 2:
            return Gesture.PEACE
        elif finger_count == 1:
            # Check if pointing up or thumb gesture
            if aspect_ratio < 0.7:  # Tall and narrow = pointing up
                return Gesture.POINTING_UP
            elif thumb_extended:
                # Check thumb direction based on position
                if center_y < 0.5:  # Hand in upper half
                    return Gesture.THUMBS_UP
                else:
                    return Gesture.THUMBS_DOWN
        elif finger_count == 0 and solidity > 0.8:
            return Gesture.FIST
        
        return Gesture.NONE

    def detect(self, frame: NDArray[np.uint8]) -> Gesture:
        """Detect gesture in frame.
        
        Args:
            frame: BGR image from camera
            
        Returns:
            Detected gesture
        """
        try:
            # Detect skin
            mask = self._detect_skin(frame)
            
            # Find hand contour
            contour = self._find_hand_contour(mask)
            
            if contour is None:
                return Gesture.NONE
            
            # Classify gesture
            return self._classify_gesture(contour, frame.shape[0])
            
        except Exception as e:
            logger.debug("Gesture detection error: %s", e)
            return Gesture.NONE

    def process_frame(self, frame: NDArray[np.uint8]) -> Optional[Gesture]:
        """Process frame and trigger callbacks if gesture held."""
        current_gesture = self.detect(frame)
        current_time = time.time()
        
        # Update current gesture for HA entity
        if current_gesture != Gesture.NONE:
            self._current_gesture = current_gesture
            self._last_gesture_time = current_time
        elif current_time - self._last_gesture_time > self._gesture_clear_delay:
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
                self._last_trigger_time = current_time
                self._gesture_start_time = None
                
                callback = self._get_callback_for_gesture(current_gesture)
                if callback:
                    logger.info("Gesture triggered: %s", current_gesture.value)
                    try:
                        callback()
                    except Exception as e:
                        logger.error("Gesture callback error: %s", e)
                    return current_gesture
        
        return None

    def _get_callback_for_gesture(self, gesture: Gesture) -> Optional[Callable[[], None]]:
        """Get callback for gesture."""
        callbacks = {
            Gesture.THUMBS_UP: self._on_thumbs_up,
            Gesture.THUMBS_DOWN: self._on_thumbs_down,
            Gesture.OPEN_PALM: self._on_open_palm,
            Gesture.FIST: self._on_fist,
            Gesture.PEACE: self._on_peace,
            Gesture.POINTING_UP: self._on_pointing_up,
        }
        return callbacks.get(gesture)

    def close(self) -> None:
        """Release resources."""
        pass
