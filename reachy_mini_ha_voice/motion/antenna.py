"""Antenna control module for Reachy Mini.

This module handles antenna freeze/unfreeze logic for listening mode,
and antenna blending during state transitions.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Antenna control constants
ANTENNA_BLEND_DURATION = 0.5  # Seconds to blend back from frozen state
DEFAULT_ANTENNA_POSITION = 0.0  # Neutral antenna position in radians


@dataclass
class AntennaState:
    """State container for antenna control.

    This can be used standalone or integrated with MovementState.
    """

    # Frozen state (for listening mode)
    frozen: bool = False
    frozen_left: float = 0.0
    frozen_right: float = 0.0

    # Blend progress (0.0 = fully frozen, 1.0 = fully unfrozen)
    blend: float = 1.0
    blend_start_time: float = 0.0

    # Target positions
    target_left: float = 0.0
    target_right: float = 0.0

    # Animation offsets
    anim_left: float = 0.0
    anim_right: float = 0.0


class AntennaController:
    """Controller for antenna freeze/unfreeze behavior.

    This class manages the antenna state during listening mode,
    where antennas should freeze at their current position and
    smoothly blend back when exiting listening mode.

    Usage:
        controller = AntennaController(time_func=time.monotonic)
        controller.freeze(current_left=0.1, current_right=-0.1)
        # ... later ...
        controller.start_unfreeze()
        # ... in control loop ...
        controller.update(dt=0.01)
        left, right = controller.get_blended_positions(target_left, target_right)
    """

    def __init__(
        self,
        time_func=None,
        blend_duration: float = ANTENNA_BLEND_DURATION,
    ):
        """Initialize the antenna controller.

        Args:
            time_func: Function returning current time (e.g., time.monotonic)
            blend_duration: Duration in seconds for blend transitions
        """
        import time

        self._now = time_func or time.monotonic
        self._blend_duration = blend_duration

        # State
        self._frozen = False
        self._frozen_left = 0.0
        self._frozen_right = 0.0
        self._blend = 1.0  # 0.0 = frozen, 1.0 = unfrozen
        self._blend_start_time = 0.0

    @property
    def is_frozen(self) -> bool:
        """Check if antennas are currently frozen."""
        return self._frozen

    @property
    def blend(self) -> float:
        """Get current blend factor (0.0 = frozen, 1.0 = unfrozen)."""
        return self._blend

    def freeze(self, current_left: float, current_right: float) -> None:
        """Freeze antennas at current position.

        Called when entering listening mode.

        Args:
            current_left: Current left antenna position in radians
            current_right: Current right antenna position in radians
        """
        self._frozen = True
        self._frozen_left = current_left
        self._frozen_right = current_right
        self._blend = 0.0  # Fully frozen
        logger.debug("Antennas frozen at left=%.3f, right=%.3f", current_left, current_right)

    def start_unfreeze(self) -> None:
        """Start unfreezing antennas with smooth blend.

        Called when exiting listening mode.
        """
        if not self._frozen:
            return

        self._blend_start_time = self._now()
        logger.debug("Starting antenna unfreeze")

    def update(self, dt: float = None) -> None:
        """Update blend state for smooth unfreezing.

        Should be called each control loop iteration.

        Args:
            dt: Delta time (not used directly, but kept for API consistency)
        """
        if not self._frozen:
            return

        if self._blend >= 1.0:
            # Fully unfrozen
            self._frozen = False
            return

        # Calculate blend progress
        elapsed = self._now() - self._blend_start_time
        if elapsed > 0:
            self._blend = min(1.0, elapsed / self._blend_duration)

            if self._blend >= 1.0:
                self._frozen = False
                logger.debug("Antennas unfrozen")

    def get_blended_positions(
        self,
        target_left: float,
        target_right: float,
    ) -> tuple[float, float]:
        """Get antenna positions with freeze blending applied.

        Args:
            target_left: Target left antenna position
            target_right: Target right antenna position

        Returns:
            Tuple of (left_position, right_position) with blending applied
        """
        if not self._frozen or self._blend >= 1.0:
            return target_left, target_right

        # Blend between frozen and target positions
        blend = self._blend
        left = self._frozen_left * (1.0 - blend) + target_left * blend
        right = self._frozen_right * (1.0 - blend) + target_right * blend

        return left, right

    def reset(self) -> None:
        """Reset antenna state to default (unfrozen)."""
        self._frozen = False
        self._frozen_left = 0.0
        self._frozen_right = 0.0
        self._blend = 1.0


def calculate_antenna_blend(
    frozen_pos: float,
    target_pos: float,
    blend: float,
) -> float:
    """Calculate blended antenna position.

    Helper function for single antenna blending.

    Args:
        frozen_pos: Position when frozen
        target_pos: Target position
        blend: Blend factor (0.0 = frozen, 1.0 = target)

    Returns:
        Blended antenna position
    """
    if blend >= 1.0:
        return target_pos
    if blend <= 0.0:
        return frozen_pos
    return frozen_pos * (1.0 - blend) + target_pos * blend
