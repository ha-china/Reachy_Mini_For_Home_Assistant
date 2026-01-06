"""Tap detection using IMU accelerometer data.

This module provides tap/knock detection for Reachy Mini (Wireless version only).
When a tap is detected, it can trigger the voice assistant wake-up.
"""

import logging
import math
import threading
import time
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

_LOGGER = logging.getLogger(__name__)

# Tap detection parameters
TAP_THRESHOLD_G_DEFAULT = 2.0  # Default acceleration threshold in g
TAP_THRESHOLD_G_MIN = 0.5  # Minimum threshold (very sensitive)
TAP_THRESHOLD_G_MAX = 5.0  # Maximum threshold (less sensitive)
TAP_COOLDOWN_SECONDS = 1.0  # Minimum time between tap detections
TAP_DETECTION_RATE_HZ = 50  # IMU polling rate


class TapDetector:
    """Detects taps/knocks on Reachy Mini using IMU accelerometer."""

    def __init__(
        self,
        reachy_mini: Optional["ReachyMini"] = None,
        on_tap_callback: Optional[Callable[[], None]] = None,
        threshold_g: float = TAP_THRESHOLD_G_DEFAULT,
        cooldown_seconds: float = TAP_COOLDOWN_SECONDS,
    ):
        """Initialize tap detector.
        
        Args:
            reachy_mini: Reachy Mini robot instance
            on_tap_callback: Callback function when tap is detected
            threshold_g: Acceleration threshold in g units (0.5-5.0)
            cooldown_seconds: Minimum time between tap detections
        """
        self.reachy_mini = reachy_mini
        self._on_tap_callback = on_tap_callback
        self._threshold_g = threshold_g
        self._threshold_ms2 = threshold_g * 9.81
        self._cooldown_seconds = cooldown_seconds
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_tap_time: float = 0.0
        self._enabled = True
        self._baseline_magnitude: float = 9.81

    @property
    def threshold_g(self) -> float:
        """Get current threshold in g units."""
        return self._threshold_g

    @threshold_g.setter
    def threshold_g(self, value: float) -> None:
        """Set threshold in g units (clamped to valid range)."""
        value = max(TAP_THRESHOLD_G_MIN, min(TAP_THRESHOLD_G_MAX, value))
        self._threshold_g = value
        self._threshold_ms2 = value * 9.81
        _LOGGER.info("Tap threshold set to %.2fg", value)

    def set_reachy_mini(self, reachy_mini: "ReachyMini") -> None:
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini

    def set_callback(self, callback: Callable[[], None]) -> None:
        """Set the tap detection callback."""
        self._on_tap_callback = callback

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable tap detection."""
        self._enabled = enabled
        _LOGGER.info("Tap detection %s", "enabled" if enabled else "disabled")

    @property
    def is_running(self) -> bool:
        """Check if tap detector is running."""
        return self._running

    def start(self) -> None:
        """Start tap detection thread."""
        if self._running:
            _LOGGER.warning("TapDetector already running")
            return
        
        if self.reachy_mini is None:
            _LOGGER.warning("Cannot start TapDetector: no Reachy Mini instance")
            return
        
        # Check if IMU is available (Wireless version only)
        try:
            imu_data = self.reachy_mini.imu
            if imu_data is None:
                _LOGGER.warning(
                    "IMU not available - tap detection disabled "
                    "(only available on Wireless version)"
                )
                return
        except Exception as e:
            _LOGGER.warning("Failed to check IMU availability: %s", e)
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="tap-detector"
        )
        self._thread.start()
        _LOGGER.info("TapDetector started (threshold=%.1fg)", self._threshold_ms2 / 9.81)

    def stop(self) -> None:
        """Stop tap detection thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        _LOGGER.info("TapDetector stopped")

    def _calibrate_baseline(self) -> None:
        """Calibrate baseline acceleration (gravity)."""
        samples = []
        for _ in range(20):
            if not self._running or self.reachy_mini is None:
                break
            try:
                imu = self.reachy_mini.imu
                if imu and "accelerometer" in imu:
                    ax, ay, az = imu["accelerometer"]
                    samples.append(math.sqrt(ax*ax + ay*ay + az*az))
            except Exception:
                pass
            time.sleep(0.02)
        
        if samples:
            self._baseline_magnitude = sum(samples) / len(samples)
            _LOGGER.info("IMU baseline calibrated: %.2f m/s²", self._baseline_magnitude)

    def _detection_loop(self) -> None:
        """Main detection loop running in background thread."""
        _LOGGER.debug("Tap detection loop started")
        
        # Calibration phase
        self._calibrate_baseline()
        
        interval = 1.0 / TAP_DETECTION_RATE_HZ
        
        while self._running:
            try:
                if not self._enabled or self.reachy_mini is None:
                    time.sleep(interval)
                    continue
                
                imu = self.reachy_mini.imu
                if not imu or "accelerometer" not in imu:
                    time.sleep(interval)
                    continue
                
                # Get accelerometer data
                ax, ay, az = imu["accelerometer"]
                magnitude = math.sqrt(ax*ax + ay*ay + az*az)
                
                # Detect tap: sudden spike above baseline + threshold
                delta = abs(magnitude - self._baseline_magnitude)
                
                if delta > self._threshold_ms2:
                    now = time.time()
                    if now - self._last_tap_time > self._cooldown_seconds:
                        self._last_tap_time = now
                        _LOGGER.info("Tap detected! (delta=%.2f m/s²)", delta)
                        
                        if self._on_tap_callback:
                            try:
                                self._on_tap_callback()
                            except Exception as e:
                                _LOGGER.error("Tap callback error: %s", e)
                
                time.sleep(interval)
                
            except Exception as e:
                _LOGGER.debug("Tap detection error: %s", e)
                time.sleep(0.1)
        
        _LOGGER.debug("Tap detection loop stopped")
