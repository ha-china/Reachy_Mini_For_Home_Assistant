"""Direction of Arrival (DOA) sound localization tracker.

This module implements sound source tracking using the microphone array's
DOA (Direction of Arrival) data to make the robot turn towards sounds
when idle.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DOAConfig:
    """Configuration for DOA tracking behavior."""

    # Minimum energy threshold to consider a sound significant
    energy_threshold: float = 0.3

    # Minimum angle change (degrees) to trigger a turn
    angle_threshold_deg: float = 15.0

    # Cooldown time (seconds) before responding to same direction
    direction_cooldown: float = 5.0

    # Duration of turn animation (seconds)
    turn_duration: float = 1.5

    # Number of direction zones for cooldown tracking
    num_zones: int = 8

    # Maximum turn angle (degrees)
    max_turn_angle_deg: float = 60.0

    # Minimum time between any turns (seconds)
    min_turn_interval: float = 2.0


class DOATracker:
    """Tracks sound direction and triggers head turns when idle.

    This class monitors DOA (Direction of Arrival) data from the microphone
    array and triggers smooth head turns towards sound sources when the
    robot is idle and not tracking a face.

    Usage:
        tracker = DOATracker(movement_callback=robot.turn_to_angle)

        # In audio processing loop:
        tracker.update(doa_angle=45.0, energy=0.5)
    """

    def __init__(
        self,
        movement_callback: Callable[[float, float], None] | None = None,
        config: DOAConfig | None = None,
    ):
        """Initialize the DOA tracker.

        Args:
            movement_callback: Function to call for turning.
                               Signature: (yaw_degrees, duration) -> None
            config: DOA tracking configuration
        """
        self._movement_callback = movement_callback
        self._config = config or DOAConfig()

        # State
        self._enabled = True
        self._face_detected = False
        self._in_conversation = False
        self._last_angle: float = 0.0
        self._last_turn_time: float = 0.0

        # Zone-based cooldown tracking
        self._zone_cooldowns: dict[int, float] = {}

        # Time function
        self._now = time.monotonic

    @property
    def enabled(self) -> bool:
        """Check if DOA tracking is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable DOA tracking."""
        self._enabled = value
        if value:
            logger.debug("DOA tracking enabled")
        else:
            logger.debug("DOA tracking disabled")

    def set_face_detected(self, detected: bool) -> None:
        """Update face detection state.

        DOA tracking is suppressed when a face is detected.
        """
        self._face_detected = detected

    def set_conversation_mode(self, in_conversation: bool) -> None:
        """Update conversation mode state.

        DOA tracking is suppressed during conversation.
        """
        self._in_conversation = in_conversation

    def set_movement_callback(self, callback: Callable[[float, float], None]) -> None:
        """Set the movement callback function.

        Args:
            callback: Function(yaw_degrees, duration) to call for turning
        """
        self._movement_callback = callback

    def update(self, doa_angle: float, energy: float) -> bool:
        """Process DOA data and trigger turn if appropriate.

        Args:
            doa_angle: Direction of arrival in degrees (-180 to 180)
            energy: Sound energy level (0 to 1)

        Returns:
            True if a turn was triggered, False otherwise
        """
        # Check if tracking should be active
        if not self._should_track():
            return False

        # Check energy threshold
        if energy < self._config.energy_threshold:
            return False

        # Check angle change threshold
        angle_diff = abs(doa_angle - self._last_angle)
        if angle_diff < self._config.angle_threshold_deg:
            return False

        # Check minimum turn interval
        now = self._now()
        if now - self._last_turn_time < self._config.min_turn_interval:
            return False

        # Check zone cooldown
        zone = self._get_zone(doa_angle)
        zone_last_time = self._zone_cooldowns.get(zone, 0)
        if now - zone_last_time < self._config.direction_cooldown:
            logger.debug(f"DOA zone {zone} in cooldown")
            return False

        # Clamp angle
        clamped_angle = max(-self._config.max_turn_angle_deg, min(self._config.max_turn_angle_deg, doa_angle))

        # Trigger turn
        if self._movement_callback:
            logger.info(f"DOA turn triggered: {clamped_angle:.1f}° (energy={energy:.2f})")
            self._movement_callback(clamped_angle, self._config.turn_duration)

            # Update state
            self._last_angle = doa_angle
            self._last_turn_time = now
            self._zone_cooldowns[zone] = now

            return True

        return False

    def _should_track(self) -> bool:
        """Check if DOA tracking should be active."""
        if not self._enabled:
            return False

        if self._face_detected:
            return False

        return not self._in_conversation

    def _get_zone(self, angle: float) -> int:
        """Get the direction zone for an angle.

        Divides the 360° space into zones for cooldown tracking.
        """
        # Normalize to 0-360
        normalized = (angle + 180) % 360

        # Calculate zone
        zone_size = 360 / self._config.num_zones
        return int(normalized / zone_size)

    def reset_cooldowns(self) -> None:
        """Reset all zone cooldowns."""
        self._zone_cooldowns.clear()
        self._last_turn_time = 0.0
        logger.debug("DOA cooldowns reset")
