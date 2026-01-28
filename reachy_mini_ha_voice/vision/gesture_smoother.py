"""Gesture smoothing and confirmation system.

This module implements gesture tracking using history tracking
without confidence filtering, following the reference implementation.

Reference: @reference/dynamic_gestures/main_controller.py
"""

import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class GestureSmoother:
    """Smooths gesture detections using history tracking.

    Unlike the reference implementation which uses KalmanBoxTracker + OCSort,
    this simpler version uses history tracking without spatial tracking.

    Key principles from reference:
    1. NO confidence filtering - pass all detections
    2. Use history to stabilize gesture output
    3. Return the most frequently detected gesture in recent frames

    Usage:
        smoother = GestureSmoother()
        detected_gesture, confidence = gesture_detector.detect(frame)
        confirmed_gesture = smoother.update(detected_gesture, confidence)
    """

    def __init__(self, history_size: int = 5):
        """Initialize gesture smoother.

        Args:
            history_size: Number of recent frames to track (default: 5)
        """
        self.history_size = history_size
        self._history: deque[tuple[str, float]] = deque(maxlen=history_size)
        self._confirmed_gesture = "none"

    def update(self, gesture: str, confidence: float) -> str:
        """Update with new gesture detection and return confirmed gesture.

        This follows the reference implementation's approach:
        - Track all detections without filtering
        - Return the most frequent gesture in recent history
        - If "none" is dominant, return "none"

        Args:
            gesture: Gesture name (e.g., "like", "peace", "none")
            confidence: Detection confidence (0.0-1.0)

        Returns:
            Confirmed gesture name based on history
        """
        # Add to history
        self._history.append((gesture, confidence))

        # Count occurrences of each gesture in history
        gesture_counts = {}
        for g, _ in self._history:
            gesture_counts[g] = gesture_counts.get(g, 0) + 1

        # Find the most frequent gesture
        if not gesture_counts:
            return "none"

        # Get gesture with highest count
        most_frequent = max(gesture_counts, key=gesture_counts.get)

        # If "none" is most frequent, return "none"
        if most_frequent == "none":
            self._confirmed_gesture = "none"
        else:
            # Otherwise return the most frequent non-none gesture
            # This is more responsive than requiring consecutive matches
            self._confirmed_gesture = most_frequent

        return self._confirmed_gesture