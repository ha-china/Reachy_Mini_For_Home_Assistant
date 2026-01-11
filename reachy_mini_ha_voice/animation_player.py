"""Animation player for conversation state animations.

This module provides a JSON-driven animation system for Reachy Mini,
inspired by SimpleDances project and reachy_mini_conversation_app.

Animations are defined as periodic oscillations that can be layered
on top of other movements. The speaking animation uses multi-frequency
oscillators for more natural head sway.
"""

import json
import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

_LOGGER = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).parent
_ANIMATIONS_FILE = _MODULE_DIR / "animations" / "conversation_animations.json"


@dataclass
class AnimationParams:
    """Parameters for a single animation with per-axis frequencies."""
    name: str
    description: str
    # Position amplitudes (meters)
    x_amplitude_m: float = 0.0
    y_amplitude_m: float = 0.0
    z_amplitude_m: float = 0.0
    # Position offsets (meters)
    x_offset_m: float = 0.0
    y_offset_m: float = 0.0
    z_offset_m: float = 0.0
    # Orientation amplitudes (radians)
    roll_amplitude_rad: float = 0.0
    pitch_amplitude_rad: float = 0.0
    yaw_amplitude_rad: float = 0.0
    # Orientation offsets (radians)
    roll_offset_rad: float = 0.0
    pitch_offset_rad: float = 0.0
    yaw_offset_rad: float = 0.0
    # Antenna
    antenna_amplitude_rad: float = 0.0
    antenna_move_name: str = "both"
    # Per-axis frequencies (Hz) - if not specified, uses main frequency_hz
    frequency_hz: float = 0.5
    pitch_frequency_hz: float = 0.0
    yaw_frequency_hz: float = 0.0
    roll_frequency_hz: float = 0.0
    x_frequency_hz: float = 0.0
    y_frequency_hz: float = 0.0
    z_frequency_hz: float = 0.0
    # Phase offset for variation
    phase_offset: float = 0.0


class AnimationPlayer:
    """Plays JSON-defined animations for conversation states.

    Features:
    - Multi-frequency oscillators for natural motion
    - Random phase offsets per animation start for variation
    - Smooth transitions between animations
    """

    def __init__(self):
        self._animations: Dict[str, AnimationParams] = {}
        self._amplitude_scale: float = 1.0
        self._transition_duration: float = 0.3
        self._current_animation: Optional[str] = None
        self._target_animation: Optional[str] = None
        self._transition_start: float = 0.0
        self._phase_start: float = 0.0
        self._lock = threading.Lock()
        # Random phase offsets for each axis (regenerated on animation change)
        self._phase_pitch: float = 0.0
        self._phase_yaw: float = 0.0
        self._phase_roll: float = 0.0
        self._phase_x: float = 0.0
        self._phase_y: float = 0.0
        self._phase_z: float = 0.0
        self._load_animations()

    def _load_animations(self) -> None:
        """Load animations from JSON file."""
        if not _ANIMATIONS_FILE.exists():
            _LOGGER.warning("Animations file not found: %s", _ANIMATIONS_FILE)
            return
        try:
            with open(_ANIMATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            settings = data.get("settings", {})
            self._amplitude_scale = settings.get("amplitude_scale", 1.0)
            self._transition_duration = settings.get("transition_duration_s", 0.3)
            animations = data.get("animations", {})
            for name, params in animations.items():
                self._animations[name] = AnimationParams(
                    name=name,
                    description=params.get("description", ""),
                    x_amplitude_m=params.get("x_amplitude_m", 0.0),
                    y_amplitude_m=params.get("y_amplitude_m", 0.0),
                    z_amplitude_m=params.get("z_amplitude_m", 0.0),
                    x_offset_m=params.get("x_offset_m", 0.0),
                    y_offset_m=params.get("y_offset_m", 0.0),
                    z_offset_m=params.get("z_offset_m", 0.0),
                    roll_amplitude_rad=params.get("roll_amplitude_rad", 0.0),
                    pitch_amplitude_rad=params.get("pitch_amplitude_rad", 0.0),
                    yaw_amplitude_rad=params.get("yaw_amplitude_rad", 0.0),
                    roll_offset_rad=params.get("roll_offset_rad", 0.0),
                    pitch_offset_rad=params.get("pitch_offset_rad", 0.0),
                    yaw_offset_rad=params.get("yaw_offset_rad", 0.0),
                    antenna_amplitude_rad=params.get("antenna_amplitude_rad", 0.0),
                    antenna_move_name=params.get("antenna_move_name", "both"),
                    frequency_hz=params.get("frequency_hz", 0.5),
                    pitch_frequency_hz=params.get("pitch_frequency_hz", 0.0),
                    yaw_frequency_hz=params.get("yaw_frequency_hz", 0.0),
                    roll_frequency_hz=params.get("roll_frequency_hz", 0.0),
                    x_frequency_hz=params.get("x_frequency_hz", 0.0),
                    y_frequency_hz=params.get("y_frequency_hz", 0.0),
                    z_frequency_hz=params.get("z_frequency_hz", 0.0),
                    phase_offset=params.get("phase_offset", 0.0),
                )
            _LOGGER.info("Loaded %d animations", len(self._animations))
        except Exception as e:
            _LOGGER.error("Failed to load animations: %s", e)

    def _randomize_phases(self) -> None:
        """Generate random phase offsets for natural variation."""
        self._phase_pitch = random.random() * 2 * math.pi
        self._phase_yaw = random.random() * 2 * math.pi
        self._phase_roll = random.random() * 2 * math.pi
        self._phase_x = random.random() * 2 * math.pi
        self._phase_y = random.random() * 2 * math.pi
        self._phase_z = random.random() * 2 * math.pi

    def set_animation(self, name: str) -> bool:
        """Set the current animation with smooth transition."""
        with self._lock:
            if name not in self._animations and name is not None:
                _LOGGER.warning("Unknown animation: %s", name)
                return False
            if name == self._current_animation:
                return True
            self._target_animation = name
            self._transition_start = time.perf_counter()
            # Randomize phases for new animation
            self._randomize_phases()
            _LOGGER.debug("Transitioning to animation: %s", name)
            return True

    def stop(self) -> None:
        """Stop all animations."""
        with self._lock:
            self._current_animation = None
            self._target_animation = None

    def get_offsets(self, dt: float = 0.0) -> Dict[str, float]:
        """Calculate current animation offsets.

        Uses multi-frequency oscillators for natural motion.
        Each axis can have its own frequency for more organic movement.

        Args:
            dt: Delta time (unused, kept for API compatibility)

        Returns:
            Dict with keys: pitch, yaw, roll, x, y, z, antenna_left, antenna_right
        """
        with self._lock:
            now = time.perf_counter()

            # Handle transition
            if self._target_animation != self._current_animation:
                elapsed = now - self._transition_start
                if elapsed >= self._transition_duration:
                    self._current_animation = self._target_animation
                    self._phase_start = now

            # No animation
            if self._current_animation is None:
                return {
                    "pitch": 0.0, "yaw": 0.0, "roll": 0.0,
                    "x": 0.0, "y": 0.0, "z": 0.0,
                    "antenna_left": 0.0, "antenna_right": 0.0,
                }

            params = self._animations.get(self._current_animation)
            if params is None:
                return {
                    "pitch": 0.0, "yaw": 0.0, "roll": 0.0,
                    "x": 0.0, "y": 0.0, "z": 0.0,
                    "antenna_left": 0.0, "antenna_right": 0.0,
                }

            elapsed = now - self._phase_start
            base_freq = params.frequency_hz

            # Calculate blend factor for smooth transitions
            blend = 1.0
            if self._target_animation != self._current_animation:
                blend = min((now - self._transition_start) / self._transition_duration, 1.0)

            # Per-axis frequencies (fall back to base frequency if not specified)
            pitch_freq = params.pitch_frequency_hz if params.pitch_frequency_hz > 0 else base_freq
            yaw_freq = params.yaw_frequency_hz if params.yaw_frequency_hz > 0 else base_freq
            roll_freq = params.roll_frequency_hz if params.roll_frequency_hz > 0 else base_freq
            x_freq = params.x_frequency_hz if params.x_frequency_hz > 0 else base_freq
            y_freq = params.y_frequency_hz if params.y_frequency_hz > 0 else base_freq
            z_freq = params.z_frequency_hz if params.z_frequency_hz > 0 else base_freq

            # Calculate oscillations with per-axis frequencies and random phases
            pitch = (params.pitch_offset_rad +
                     params.pitch_amplitude_rad *
                     math.sin(2 * math.pi * pitch_freq * elapsed + self._phase_pitch))

            yaw = (params.yaw_offset_rad +
                   params.yaw_amplitude_rad *
                   math.sin(2 * math.pi * yaw_freq * elapsed + self._phase_yaw))

            roll = (params.roll_offset_rad +
                    params.roll_amplitude_rad *
                    math.sin(2 * math.pi * roll_freq * elapsed + self._phase_roll))

            x = (params.x_offset_m +
                 params.x_amplitude_m *
                 math.sin(2 * math.pi * x_freq * elapsed + self._phase_x))

            y = (params.y_offset_m +
                 params.y_amplitude_m *
                 math.sin(2 * math.pi * y_freq * elapsed + self._phase_y))

            z = (params.z_offset_m +
                 params.z_amplitude_m *
                 math.sin(2 * math.pi * z_freq * elapsed + self._phase_z))

            # Antenna movement
            antenna_phase = 2 * math.pi * base_freq * elapsed
            if params.antenna_move_name == "both":
                left = right = params.antenna_amplitude_rad * math.sin(antenna_phase)
            elif params.antenna_move_name == "wiggle":
                left = params.antenna_amplitude_rad * math.sin(antenna_phase)
                right = params.antenna_amplitude_rad * math.sin(antenna_phase + math.pi)
            else:
                left = params.antenna_amplitude_rad * math.sin(antenna_phase)
                right = params.antenna_amplitude_rad * math.sin(antenna_phase + math.pi / 2)

            # Apply scale and blend
            scale = self._amplitude_scale * blend
            return {
                "pitch": pitch * scale,
                "yaw": yaw * scale,
                "roll": roll * scale,
                "x": x * scale,
                "y": y * scale,
                "z": z * scale,
                "antenna_left": left * scale,
                "antenna_right": right * scale,
            }

    @property
    def current_animation(self) -> Optional[str]:
        """Get the current animation name."""
        with self._lock:
            return self._current_animation

    @property
    def available_animations(self) -> list:
        """Get list of available animation names."""
        return list(self._animations.keys())
