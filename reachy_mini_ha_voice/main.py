"""
Reachy Mini for Home Assistant Application

This is the main entry point for the Reachy Mini application that integrates
with Home Assistant via ESPHome protocol for voice control.
"""

import asyncio
import logging
import socket
import threading

from .voice_assistant import VoiceAssistantService

logger = logging.getLogger(__name__)


def _check_zenoh_available(timeout: float = 1.0) -> bool:
    """Check if Zenoh service is available."""
    try:
        with socket.create_connection(("127.0.0.1", 7447), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


# Only import ReachyMiniApp if we're running as an app
try:
    from reachy_mini import ReachyMini, ReachyMiniApp
    REACHY_MINI_AVAILABLE = True
except ImportError:
    REACHY_MINI_AVAILABLE = False

    # Create a dummy base class
    class ReachyMiniApp:
        custom_app_url = None

        def __init__(self):
            self.stop_event = threading.Event()

        def wrapped_run(self, *args, **kwargs):
            pass

        def stop(self):
            self.stop_event.set()

    ReachyMini = None


class ReachyMiniHaVoice(ReachyMiniApp):
    """
    Reachy Mini for Home Assistant Application.

    This app runs an ESPHome-compatible server that connects
    to Home Assistant for STT/TTS processing while providing local
    wake word detection and robot motion feedback.
    """

    # No custom web UI needed - configuration is automatic via Home Assistant
    custom_app_url: str | None = None

    def __init__(self, *args, **kwargs):
        """Initialize the app."""
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'stop_event'):
            self.stop_event = threading.Event()

    def wrapped_run(self, *args, **kwargs) -> None:
        """
        Override wrapped_run to handle Zenoh connection failures gracefully.

        If Zenoh is not available, run in standalone mode without robot control.
        """
        logger.info("Starting Reachy Mini HA Voice App...")

        # Check if Zenoh is available before trying to connect
        if not _check_zenoh_available():
            logger.warning("Zenoh service not available (port 7447)")
            logger.info("Running in standalone mode without robot control")
            self._run_standalone()
            return

        # Zenoh is available, try normal startup with ReachyMini
        if REACHY_MINI_AVAILABLE:
            try:
                logger.info("Attempting to connect to Reachy Mini...")
                super().wrapped_run(*args, **kwargs)
            except TimeoutError as e:
                logger.warning(f"Timeout connecting to Reachy Mini: {e}")
                logger.info("Falling back to standalone mode")
                self._run_standalone()
            except Exception as e:
                error_str = str(e)
                if "Unable to connect" in error_str or "ZError" in error_str or "Timeout" in error_str:
                    logger.warning(f"Failed to connect to Reachy Mini: {e}")
                    logger.info("Falling back to standalone mode")
                    self._run_standalone()
                else:
                    raise
        else:
            logger.info("Reachy Mini SDK not available, running standalone")
            self._run_standalone()

    def _run_standalone(self) -> None:
        """Run in standalone mode without robot."""
        self.run(None, self.stop_event)

    def run(self, reachy_mini, stop_event: threading.Event) -> None:
        """
        Main application entry point.

        Args:
            reachy_mini: The Reachy Mini robot instance (can be None)
            stop_event: Event to signal graceful shutdown
        """
        logger.info("Starting Reachy Mini for Home Assistant...")

        # Create and run the HA service
        service = VoiceAssistantService(reachy_mini)

        # Always create a new event loop to avoid conflicts with SDK
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug("Created new event loop for HA service")

        try:
            loop.run_until_complete(service.start())

            logger.info("=" * 50)
            logger.info("Reachy Mini for Home Assistant Started!")
            logger.info("=" * 50)
            logger.info("ESPHome Server: 0.0.0.0:6053")
            logger.info("Camera Server: 0.0.0.0:8081")
            logger.info("Wake word: Okay Nabu")
            if reachy_mini:
                logger.info("Motion control: enabled")
                logger.info("Camera: enabled (Reachy Mini)")
            else:
                logger.info("Motion control: disabled (no robot)")
                logger.info("Camera: test pattern (no robot)")
            logger.info("=" * 50)
            logger.info("To connect from Home Assistant:")
            logger.info("  Settings -> Devices & Services -> Add Integration")
            logger.info("  -> ESPHome -> Enter this device's IP:6053")
            logger.info("  -> Generic Camera -> http://<ip>:8081/stream")
            logger.info("=" * 50)

            # Wait for stop signal - keep event loop running
            # We need to keep the event loop alive to handle ESPHome connections
            while not stop_event.is_set():
                loop.run_until_complete(asyncio.sleep(0.1))

        except KeyboardInterrupt:
            logger.info("Keyboard interruption in main thread... closing server.")
        except Exception as e:
            logger.error(f"Error running Reachy Mini HA: {e}")
            raise
        finally:
            logger.info("Shutting down Reachy Mini HA...")
            try:
                loop.run_until_complete(service.stop())
            except Exception as e:
                logger.error(f"Error stopping service: {e}")

            # Note: Robot connection cleanup is handled by SDK's context manager
            # in wrapped_run(). We only need to close our event loop here.

            # Close event loop
            try:
                loop.close()
            except Exception as e:
                logger.debug(f"Error closing event loop: {e}")

            logger.info("Reachy Mini HA stopped.")


# This is called when running as: python -m reachy_mini_ha_voice.main
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app = ReachyMiniHaVoice()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
