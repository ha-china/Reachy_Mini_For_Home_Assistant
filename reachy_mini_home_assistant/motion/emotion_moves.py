"""Emotion moves for the MovementManager system.

This module implements emotion moves using the SDK's RecordedMoves API
that can be queued and executed by the MovementManager control loop.

Using RecordedMoves.evaluate(t) instead of the HTTP API prevents conflicts
with set_target() calls, avoiding "a move is currently running" warnings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Lazy emotion library initialization to avoid blocking app import/startup.
try:
    from reachy_mini.motion.recorded_move import RecordedMoves
    from reachy_mini.utils import create_head_pose

    RECORDED_MOVES: RecordedMoves | None = None
    EMOTION_AVAILABLE = True
    _EMOTION_INIT_ATTEMPTED = False
except Exception as e:
    logger.warning("Emotion library not available: %s", e)
    RECORDED_MOVES = None
    EMOTION_AVAILABLE = False
    _EMOTION_INIT_ATTEMPTED = True


def _ensure_emotion_library_loaded() -> bool:
    """Initialize recorded emotions once, on demand."""
    global RECORDED_MOVES, EMOTION_AVAILABLE, _EMOTION_INIT_ATTEMPTED

    if not EMOTION_AVAILABLE:
        return False
    if RECORDED_MOVES is not None:
        return True
    if _EMOTION_INIT_ATTEMPTED:
        return False

    _EMOTION_INIT_ATTEMPTED = True
    try:
        RECORDED_MOVES = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
        logger.info("Emotion library loaded successfully")
        return True
    except Exception as e:
        logger.warning("Error loading emotion library: %s", e)
        EMOTION_AVAILABLE = False
        RECORDED_MOVES = None
        return False


def is_emotion_available() -> bool:
    """Check if emotion system is available."""
    return _ensure_emotion_library_loaded()


def list_available_emotions() -> list[str]:
    """Get list of available emotion names."""
    if not _ensure_emotion_library_loaded() or RECORDED_MOVES is None:
        return []
    try:
        return RECORDED_MOVES.list_moves()
    except Exception as e:
        logger.error(f"Error listing emotions: {e}")
        return []


class EmotionMove:
    """Emotion move that wraps SDK RecordedMoves with evaluate(t) interface.

    This class allows sampling emotion poses at each control loop tick,
    which prevents conflicts with set_target() calls that would occur
    when using the HTTP API for emotion playback.
    """

    def __init__(self, emotion_name: str):
        """Initialize an EmotionMove.

        Args:
            emotion_name: Name of the emotion (e.g., "happy1", "sad1")
        """
        if not _ensure_emotion_library_loaded() or RECORDED_MOVES is None:
            raise RuntimeError("Emotion library not available")

        self.emotion_name = emotion_name
        self._emotion_move = RECORDED_MOVES.get(emotion_name)

    @property
    def duration(self) -> float:
        """Duration of the emotion in seconds."""
        return float(self._emotion_move.duration)

    def evaluate(self, t: float) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
        """Evaluate emotion pose at time t.

        Args:
            t: Time in seconds since emotion started

        Returns:
            Tuple of (head_pose_4x4, antennas_array, body_yaw)
            - head_pose: 4x4 homogeneous transformation matrix
            - antennas: numpy array [right_angle, left_angle] in radians
            - body_yaw: body yaw angle in radians
        """
        try:
            # Get pose from the emotion move
            head_pose, antennas, body_yaw = self._emotion_move.evaluate(t)

            # Convert antennas to numpy array if needed
            if isinstance(antennas, (tuple, list)):
                antennas = np.array([antennas[0], antennas[1]], dtype=np.float64)

            return (head_pose, antennas, body_yaw)

        except Exception as e:
            logger.error(f"Error evaluating emotion '{self.emotion_name}' at t={t}: {e}")
            # Return neutral pose on error
            try:
                neutral_head_pose = create_head_pose(0, 0, 0, 0, 0, 0, degrees=True)
            except Exception:
                neutral_head_pose = np.eye(4, dtype=np.float64)

            return (neutral_head_pose, np.array([0.0, 0.0], dtype=np.float64), 0.0)
