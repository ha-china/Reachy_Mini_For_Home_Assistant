"""Gesture smoothing and confirmation system.

This module implements gesture tracking using history tracking
without confidence filtering, following the reference implementation.

Reference: @reference/dynamic_gestures/main_controller.py
"""

import logging
from collections import deque

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

    def __init__(self, history_size: int = 5, clear_grace_updates: int = 3):
        """Initialize gesture smoother.

        Args:
            history_size: Number of recent frames to track (default: 5)
            clear_grace_updates: Number of consecutive "none" detections
                required before clearing a previously confirmed gesture.
        """
        self.history_size = history_size
        self.clear_grace_updates = max(0, clear_grace_updates)
        self._history: deque[tuple[str, float]] = deque(maxlen=history_size)
        self._confirmed_gesture = "none"
        self._none_streak = 0

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

        # Fast path: non-none detections should feel immediate.
        if gesture != "none":
            self._none_streak = 0
            self._confirmed_gesture = gesture
            return self._confirmed_gesture

        # Slow clear path: avoid flicker on occasional missed detections.
        self._none_streak += 1
        if self._confirmed_gesture != "none" and self._none_streak <= self.clear_grace_updates:
            return self._confirmed_gesture

        # Count occurrences of each gesture in history
        gesture_counts: dict[str, int] = {}
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
            self._none_streak = 0

        return self._confirmed_gesture
