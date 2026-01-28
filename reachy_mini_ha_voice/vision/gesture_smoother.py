"""Gesture smoothing and confirmation system.

This module provides gesture history tracking and confirmation logic
to improve gesture detection sensitivity and reduce false positives.
"""

import logging
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GestureConfig:
    """Configuration for gesture smoothing."""

    # History buffer size (number of frames to keep)
    history_size: int = 5

    # Minimum consecutive frames to confirm gesture
    min_confirm_frames: int = 3

    # Minimum confidence threshold for detection
    confidence_threshold: float = 0.3

    # Confidence aggregation method: "max", "avg", "recent"
    confidence_method: str = "max"


class GestureSmoother:
    """Smooths and confirms gesture detections using history tracking.

    This class maintains a sliding window of recent gesture detections
    and only outputs a gesture when it has been consistently detected
    for multiple consecutive frames. This reduces false positives and
    provides smoother gesture transitions.

    Usage:
        smoother = GestureSmoother()
        detected_gesture, confidence = gesture_detector.detect(frame)
        confirmed_gesture = smoother.update(detected_gesture, confidence)
    """

    def __init__(self, config: GestureConfig | None = None):
        """Initialize gesture smoother.

        Args:
            config: Gesture smoothing configuration
        """
        self.config = config or GestureConfig()
        self._history: deque[tuple[str, float]] = deque(maxlen=self.config.history_size)
        self._confirmed_gesture = "none"
        self._current_streak = 0  # Consecutive frames of same gesture

    def update(self, gesture: str, confidence: float) -> str:
        """Update with new gesture detection and return confirmed gesture.

        Args:
            gesture: Gesture name (e.g., "like", "peace", "none")
            confidence: Detection confidence (0.0-1.0)

        Returns:
            Confirmed gesture name (only changes when gesture is confirmed)
        """
        # Add to history
        self._history.append((gesture, confidence))

        # Filter out low-confidence detections
        if gesture != "none" and confidence < self.config.confidence_threshold:
            gesture = "none"

        # Check if we have a consistent gesture
        if gesture == "none":
            # Reset streak on no gesture
            self._current_streak = 0
            # Keep last confirmed gesture for a few frames (debounce)
            if len(self._history) >= self.config.history_size - 1:
                # Check if most recent frames are all "none"
                recent_none = all(g == "none" for g, _ in list(self._history)[-3:])
                if recent_none:
                    self._confirmed_gesture = "none"
        else:
            # Check if this gesture matches the streak
            if self._current_streak == 0:
                # Start new streak
                self._current_streak = 1
            elif gesture == self._history[-2][0]:  # Same as previous frame
                self._current_streak += 1
            else:
                # Gesture changed, reset streak
                self._current_streak = 1

            # Confirm gesture if streak is long enough
            if self._current_streak >= self.config.min_confirm_frames:
                self._confirmed_gesture = gesture

        return self._confirmed_gesture

    def get_aggregated_confidence(self, gesture: str) -> float:
        """Get aggregated confidence for a specific gesture from history.

        Args:
            gesture: Gesture name to query

        Returns:
            Aggregated confidence (0.0-1.0)
        """
        matching_confidences = [c for g, c in self._history if g == gesture]

        if not matching_confidences:
            return 0.0

        if self.config.confidence_method == "max":
            return max(matching_confidences)
        elif self.config.confidence_method == "avg":
            return sum(matching_confidences) / len(matching_confidences)
        else:  # "recent"
            return matching_confidences[-1] if matching_confidences else 0.0

    def reset(self) -> None:
        """Reset gesture history and state."""
        self._history.clear()
        self._confirmed_gesture = "none"
        self._current_streak = 0

    @property
    def confirmed_gesture(self) -> str:
        """Get currently confirmed gesture."""
        return self._confirmed_gesture

    def get_history_summary(self) -> dict[str, int]:
        """Get summary of gesture counts in history.

        Returns:
            Dictionary mapping gesture names to counts
        """
        summary = {}
        for gesture, _ in self._history:
            summary[gesture] = summary.get(gesture, 0) + 1
        return summary
