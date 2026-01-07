"""Gesture detection using OpenCV skin detection and convex hull analysis.

Detects 11 hand gestures for robot interaction (no MediaPipe dependency):
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

Uses pure OpenCV - works on ARM (Raspberry Pi CM4).
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
    OK = "ok"
    ROCK = "rock"
    CALL = "call"
    THREE = "three"
    FOUR = "four"


class GestureDetector:
    """Gesture detector using OpenCV skin detection and convex hull analysis."""

    def __init__(
        self,
        min_hand_area: int = 3000,
        max_hand_area: int = 200000,
    ) -> None:
        self._min_hand_area = min_hand_area
        self._max_hand_area = max_hand_area
        
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
        
        logger.info("OpenCV gesture detector initialized (ARM compatible)")

    @property
    def is_available(self) -> bool:
        return True

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

    def _detect_skin(self, frame: NDArray[np.uint8]) -> NDArray[np.uint8]:
        """Detect skin using YCrCb and HSV color spaces."""
        # YCrCb detection
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        mask_ycrcb = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))
        
        # HSV detection for better lighting robustness
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask_hsv = cv2.inRange(hsv, np.array([0, 20, 70]), np.array([20, 255, 255]))
        
        # Combine masks
        mask = cv2.bitwise_or(mask_ycrcb, mask_hsv)
        
        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        
        return mask

    def _find_hand_contour(self, mask: NDArray[np.uint8]) -> Optional[NDArray]:
        """Find the largest hand contour."""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        valid = [(cv2.contourArea(c), c) for c in contours 
                 if self._min_hand_area < cv2.contourArea(c) < self._max_hand_area]
        
        if not valid:
            return None
        
        valid.sort(key=lambda x: x[0], reverse=True)
        return valid[0][1]

    def _count_fingers(self, contour: NDArray) -> Tuple[int, float, float]:
        """Count fingers using convex hull defects.
        
        Returns: (finger_count, hand_center_y_ratio, aspect_ratio)
        """
        hull = cv2.convexHull(contour, returnPoints=False)
        if len(hull) < 3:
            return 0, 0.5, 1.0
        
        M = cv2.moments(contour)
        if M["m00"] == 0:
            return 0, 0.5, 1.0
        
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = float(w) / h if h > 0 else 1.0
        
        # Normalize center y to frame (approximate)
        center_y_ratio = cy / (y + h) if (y + h) > 0 else 0.5
        
        try:
            defects = cv2.convexityDefects(contour, hull)
        except cv2.error:
            return 0, center_y_ratio, aspect_ratio
        
        if defects is None:
            return 0, center_y_ratio, aspect_ratio
        
        finger_count = 0
        for i in range(defects.shape[0]):
            s, e, f, d = defects[i, 0]
            start = tuple(contour[s][0])
            end = tuple(contour[e][0])
            far = tuple(contour[f][0])
            
            a = np.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
            b = np.sqrt((far[0] - start[0])**2 + (far[1] - start[1])**2)
            c = np.sqrt((end[0] - far[0])**2 + (end[1] - far[1])**2)
            
            if b * c == 0:
                continue
            
            angle = np.arccos((b**2 + c**2 - a**2) / (2 * b * c))
            
            # Finger gap if angle < 90° and defect is deep enough
            if angle <= np.pi / 2 and d > 8000:
                finger_count += 1
        
        # Defects count gaps, so fingers = gaps + 1
        if finger_count > 0:
            finger_count += 1
        
        return min(finger_count, 5), center_y_ratio, aspect_ratio

    def _get_hull_defect_info(self, contour: NDArray) -> Tuple[float, bool, bool]:
        """Get additional info from hull defects.
        
        Returns: (solidity, has_thumb_gap, has_pinky_gap)
        """
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        contour_area = cv2.contourArea(contour)
        solidity = contour_area / hull_area if hull_area > 0 else 0
        
        x, y, w, h = cv2.boundingRect(contour)
        
        # Check for gaps on sides (thumb/pinky detection)
        hull_idx = cv2.convexHull(contour, returnPoints=False)
        try:
            defects = cv2.convexityDefects(contour, hull_idx)
        except cv2.error:
            return solidity, False, False
        
        if defects is None:
            return solidity, False, False
        
        has_left_gap = False
        has_right_gap = False
        
        for i in range(defects.shape[0]):
            s, e, f, d = defects[i, 0]
            far = contour[f][0]
            
            # Check if defect is on left or right side
            if far[0] < x + w * 0.3:
                has_left_gap = True
            elif far[0] > x + w * 0.7:
                has_right_gap = True
        
        return solidity, has_left_gap, has_right_gap

    def _classify_gesture(self, contour: NDArray) -> Gesture:
        """Classify gesture based on contour analysis."""
        finger_count, center_y, aspect_ratio = self._count_fingers(contour)
        solidity, has_left_gap, has_right_gap = self._get_hull_defect_info(contour)
        
        x, y, w, h = cv2.boundingRect(contour)
        
        # Fist: no fingers, high solidity
        if finger_count == 0 and solidity > 0.75:
            return Gesture.FIST
        
        # Open palm: 4-5 fingers
        if finger_count >= 4:
            return Gesture.OPEN_PALM
        
        # Four: 4 fingers (similar to open palm but thumb tucked)
        if finger_count == 4:
            return Gesture.FOUR
        
        # Three: 3 fingers
        if finger_count == 3:
            return Gesture.THREE
        
        # Peace/Rock: 2 fingers
        if finger_count == 2:
            # Rock has gaps on both sides (index + pinky)
            if has_left_gap and has_right_gap:
                return Gesture.ROCK
            return Gesture.PEACE
        
        # One finger gestures
        if finger_count == 1:
            # Tall and narrow = pointing up
            if aspect_ratio < 0.6:
                return Gesture.POINTING_UP
            
            # Check for thumb gestures based on position
            if h > w * 1.2:  # Vertical orientation
                if center_y < 0.4:
                    return Gesture.THUMBS_UP
                elif center_y > 0.6:
                    return Gesture.THUMBS_DOWN
            
            # Call gesture: thumb + pinky (detected as 1 finger with side gaps)
            if has_left_gap and has_right_gap:
                return Gesture.CALL
            
            return Gesture.POINTING_UP
        
        # OK gesture: circular shape with moderate solidity
        if finger_count == 0 and 0.5 < solidity < 0.75:
            # Check for circular hole (OK sign)
            hull_area = cv2.contourArea(cv2.convexHull(contour))
            if hull_area > 0:
                circularity = 4 * np.pi * cv2.contourArea(contour) / (cv2.arcLength(contour, True) ** 2)
                if circularity < 0.6:  # Has a hole
                    return Gesture.OK
        
        return Gesture.NONE

    def detect(self, frame: NDArray[np.uint8]) -> Gesture:
        """Detect gesture in frame."""
        try:
            mask = self._detect_skin(frame)
            contour = self._find_hand_contour(mask)
            
            if contour is None:
                return Gesture.NONE
            
            return self._classify_gesture(contour)
        except Exception as e:
            logger.debug("Gesture detection error: %s", e)
            return Gesture.NONE

    def process_frame(self, frame: NDArray[np.uint8]) -> Optional[Gesture]:
        """Process frame and trigger callbacks if gesture held."""
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
        pass
