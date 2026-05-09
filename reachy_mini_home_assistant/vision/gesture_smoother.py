"""Gesture smoothing system.

This project favors fast recognition. Positive gestures confirm immediately,
while clearing back to ``none`` is delayed slightly to avoid flicker.
"""

import logging
from collections import deque

logger = logging.getLogger(__name__)


class GestureSmoother:
    """Smooths gesture detections with instant positive confirmation and delayed clear."""

    def __init__(self, history_size: int = 4, clear_grace_updates: int = 2):
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

        Args:
            gesture: Gesture name (e.g., "like", "peace", "none")
            confidence: Detection confidence (0.0-1.0)

        Returns:
            Confirmed gesture name based on history
        """
        # Add to history
        self._history.append((gesture, confidence))

        if gesture != "none":
            self._none_streak = 0
            self._confirmed_gesture = gesture
            return self._confirmed_gesture

        # Slow clear path: avoid flicker on occasional missed detections.
        self._none_streak += 1
        if self._confirmed_gesture != "none" and self._none_streak <= self.clear_grace_updates:
            return self._confirmed_gesture

        self._confirmed_gesture = "none"
        return self._confirmed_gesture
