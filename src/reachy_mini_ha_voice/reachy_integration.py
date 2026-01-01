"""Reachy Mini integration module."""

import logging
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class ReachyMiniIntegration:
    """Integration with Reachy Mini robot."""

    def __init__(self):
        """Initialize Reachy Mini integration."""
        self._reachy = None
        self._connected = False

    def connect(self) -> bool:
        """Connect to Reachy Mini."""
        try:
            # Import reachy-mini SDK
            # This will be installed when running on Reachy Mini
            from reachy_sdk import ReachySDK

            self._reachy = ReachySDK()
            self._connected = True
            _LOGGER.info("Connected to Reachy Mini")
            return True
        except ImportError:
            _LOGGER.warning("Reachy SDK not available, running in standalone mode")
            return False
        except Exception as e:
            _LOGGER.error("Failed to connect to Reachy Mini: %s", e)
            return False

    def disconnect(self) -> None:
        """Disconnect from Reachy Mini."""
        if self._reachy:
            try:
                self._reachy.disconnect()
                self._connected = False
                _LOGGER.info("Disconnected from Reachy Mini")
            except Exception as e:
                _LOGGER.error("Error disconnecting from Reachy Mini: %s", e)

    def on_wake_word_detected(self) -> None:
        """Handle wake word detection."""
        if not self._connected:
            return

        try:
            # Make Reachy Mini look up
            self._reachy.head.tilt.goto(20, duration=0.5, wait=True)
            self._reachy.head.pan.goto(0, duration=0.5, wait=True)
            _LOGGER.debug("Reachy Mini: Look up on wake word")
        except Exception as e:
            _LOGGER.error("Error moving Reachy Mini on wake word: %s", e)

    def on_listening(self) -> None:
        """Handle listening state."""
        if not self._connected:
            return

        try:
            # Subtle head movement to indicate listening
            self._reachy.head.pan.goto(10, duration=0.3, wait=True)
            self._reachy.head.pan.goto(-10, duration=0.6, wait=True)
            self._reachy.head.pan.goto(0, duration=0.3, wait=True)
            _LOGGER.debug("Reachy Mini: Listening head movement")
        except Exception as e:
            _LOGGER.error("Error moving Reachy Mini while listening: %s", e)

    def on_response(self) -> None:
        """Handle response state."""
        if not self._connected:
            return

        try:
            # Nod to acknowledge
            self._reachy.head.tilt.goto(10, duration=0.3, wait=True)
            self._reachy.head.tilt.goto(-10, duration=0.6, wait=True)
            self._reachy.head.tilt.goto(0, duration=0.3, wait=True)
            _LOGGER.debug("Reachy Mini: Nod on response")
        except Exception as e:
            _LOGGER.error("Error moving Reachy Mini on response: %s", e)

    def on_error(self) -> None:
        """Handle error state."""
        if not self._connected:
            return

        try:
            # Tilt head to indicate error
            self._reachy.head.tilt.goto(-20, duration=0.5, wait=True)
            _LOGGER.debug("Reachy Mini: Tilt head on error")
        except Exception as e:
            _LOGGER.error("Error moving Reachy Mini on error: %s", e)

    def on_stop(self) -> None:
        """Handle stop command."""
        if not self._connected:
            return

        try:
            # Shake head to indicate stop
            self._reachy.head.pan.goto(-15, duration=0.3, wait=True)
            self._reachy.head.pan.goto(15, duration=0.6, wait=True)
            self._reachy.head.pan.goto(0, duration=0.3, wait=True)
            _LOGGER.debug("Reachy Mini: Shake head on stop")
        except Exception as e:
            _LOGGER.error("Error moving Reachy Mini on stop: %s", e)

    def is_connected(self) -> bool:
        """Check if connected to Reachy Mini."""
        return self._connected