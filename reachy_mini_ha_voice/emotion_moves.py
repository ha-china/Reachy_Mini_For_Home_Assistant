"""Emotion moves for the movement queue system.

This module implements emotions as Move objects that can be queued
and executed by the MovementManager, similar to reachy_mini_conversation_app.
"""

from __future__ import annotations
import logging
from typing import Tuple, Optional

import numpy as np
from numpy.typing import NDArray

try:
    from reachy_mini.motion.move import Move
    from reachy_mini.motion.recorded_move import RecordedMoves
    REACHY_MINI_AVAILABLE = True
except ImportError:
    REACHY_MINI_AVAILABLE = False
    # Create dummy base class
    class Move:
        pass

logger = logging.getLogger(__name__)


class EmotionQueueMove(Move):  # type: ignore
    """Wrapper for emotion moves to work with the movement queue system."""

    def __init__(self, emotion_name: str, recorded_moves: "RecordedMoves"):
        """Initialize an EmotionQueueMove.

        Args:
            emotion_name: Name of the emotion (e.g., "happy1", "sad1")
            recorded_moves: RecordedMoves instance containing the emotion library
        """
        if not REACHY_MINI_AVAILABLE:
            raise ImportError("reachy_mini package is required for emotion moves")

        self.emotion_move = recorded_moves.get(emotion_name)
        self.emotion_name = emotion_name

    @property
    def duration(self) -> float:
        """Duration property required by official Move interface."""
        return float(self.emotion_move.duration)

    def evaluate(self, t: float) -> Tuple[Optional[NDArray[np.float64]], Optional[NDArray[np.float64]], Optional[float]]:
        """Evaluate emotion move at time t.

        Args:
            t: Time in seconds since move started

        Returns:
            Tuple of (head_pose, antennas, body_yaw)
        """
        try:
            # Get the pose from the emotion move
            head_pose, antennas, body_yaw = self.emotion_move.evaluate(t)

            # Convert to numpy array if antennas is tuple and return in official Move format
            if isinstance(antennas, tuple):
                antennas = np.array([antennas[0], antennas[1]], dtype=np.float64)

            return (head_pose, antennas, body_yaw)

        except Exception as e:
            logger.error(f"Error evaluating emotion '{self.emotion_name}' at t={t}: {e}")
            # Return neutral pose on error
            from reachy_mini.utils import create_head_pose

            neutral_head_pose = create_head_pose(0, 0, 0, 0, 0, 0, degrees=True)
            return (neutral_head_pose, np.array([0.0, 0.0], dtype=np.float64), 0.0)


# Global emotion library instance (lazy loaded)
_RECORDED_MOVES: Optional["RecordedMoves"] = None
_EMOTION_LIBRARY_AVAILABLE = False


def get_emotion_library() -> Optional["RecordedMoves"]:
    """Get or initialize the emotion library.

    Returns:
        RecordedMoves instance or None if not available
    """
    global _RECORDED_MOVES, _EMOTION_LIBRARY_AVAILABLE

    if not REACHY_MINI_AVAILABLE:
        return None

    if _RECORDED_MOVES is None and not _EMOTION_LIBRARY_AVAILABLE:
        try:
            from reachy_mini.motion.recorded_move import RecordedMoves
            # Note: huggingface_hub automatically reads HF_TOKEN from environment variables
            _RECORDED_MOVES = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
            _EMOTION_LIBRARY_AVAILABLE = True
            logger.info("Emotion library loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load emotion library: {e}")
            _EMOTION_LIBRARY_AVAILABLE = True  # Mark as attempted

    return _RECORDED_MOVES


def create_emotion_move(emotion_name: str) -> Optional[EmotionQueueMove]:
    """Create an emotion move for the given emotion name.

    Args:
        emotion_name: Name of the emotion (e.g., "happy1", "sad1")

    Returns:
        EmotionQueueMove instance or None if emotion library not available
    """
    recorded_moves = get_emotion_library()
    if recorded_moves is None:
        logger.warning(f"Cannot create emotion move '{emotion_name}': library not available")
        return None

    try:
        return EmotionQueueMove(emotion_name, recorded_moves)
    except Exception as e:
        logger.error(f"Failed to create emotion move '{emotion_name}': {e}")
        return None
