"""
Reachy Mini for Home Assistant Application

This is the main entry point for the Reachy Mini application that integrates
with Home Assistant via ESPHome protocol for voice control.
"""

import asyncio
import logging
import os
import pathlib
import sys
import threading

from reachy_mini import ReachyMiniApp

from .core import get_health_monitor, get_memory_monitor
from .voice_assistant import VoiceAssistantService

logger = logging.getLogger(__name__)


def _ensure_audio_routing_config() -> None:
    """Ensure Reachy Mini ALSA aliases exist before SDK media initialization.

    SDK 1.4.1 may pick autoaudiosrc/openal when no explicit device is found.
    Writing ~/.asoundrc early helps GStreamer select reachymini_audio_src/sink.
    """
    try:
        from reachy_mini.media.audio_utils import has_reachymini_asoundrc, write_asoundrc_to_home

        if has_reachymini_asoundrc():
            return
        write_asoundrc_to_home()
        logger.info("Generated ~/.asoundrc for Reachy Mini audio routing")
    except Exception as e:
        logger.warning("Could not ensure audio routing config before startup: %s", e)


def _patch_sdk_audio_device_resolution() -> None:
    """Force deterministic Reachy Mini audio aliases on Linux.

    SDK 1.4.x device monitor can fail and trigger autoaudiosrc/openal fallback.
    We bypass that path and always return Reachy Mini ALSA aliases once
    ~/.asoundrc is prepared, so media init uses a single deterministic route.
    """
    if not sys.platform.startswith("linux"):
        return

    try:
        from reachy_mini.media.audio_gstreamer import GStreamerAudio
        from reachy_mini.media.audio_utils import has_reachymini_asoundrc
    except Exception as e:
        logger.debug("SDK audio patch unavailable: %s", e)
        return

    original = getattr(GStreamerAudio, "_get_audio_device", None)
    if original is None or getattr(GStreamerAudio, "_ha_audio_patch_applied", False):
        return

    def _patched_get_audio_device(self, device_type: str = "Source"):
        if has_reachymini_asoundrc():
            return "reachymini_audio_sink" if device_type == "Sink" else "reachymini_audio_src"
        return original(self, device_type)

    GStreamerAudio._get_audio_device = _patched_get_audio_device
    GStreamerAudio._ha_audio_patch_applied = True
    logger.warning("Applied deterministic SDK audio alias patch (no OpenAL fallback path)")


def _normalize_home_for_audio_utils() -> None:
    """Normalize HOME on robot so SDK audio_utils resolves ~/.asoundrc reliably."""
    if not sys.platform.startswith("linux"):
        return

    current_home = os.environ.get("HOME", "")
    user = os.environ.get("USER", "pollen")
    preferred_home = f"/home/{user}"
    preferred_path = pathlib.Path(preferred_home)

    if not preferred_path.exists():
        # Fallback for environments where USER is not set as expected.
        preferred_home = "/home/pollen"
        preferred_path = pathlib.Path(preferred_home)

    if not preferred_path.exists():
        return

    # Force deterministic robot HOME for SDK Path.home() checks.
    # Only adjust when HOME is missing or points outside /home.
    if not current_home or not current_home.startswith("/home/"):
        os.environ["HOME"] = preferred_home
        logger.warning("Adjusted HOME from '%s' to '%s' for audio routing", current_home, preferred_home)


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
        if not hasattr(self, "stop_event"):
            self.stop_event = threading.Event()

    def wrapped_run(self, *args, **kwargs) -> None:
        """
        Override wrapped_run to handle Reachy Mini connection failures.
        """
        logger.info("Starting Reachy Mini HA Voice App...")

        _normalize_home_for_audio_utils()
        # Ensure audio routing config before SDK creates media pipelines.
        _ensure_audio_routing_config()
        _patch_sdk_audio_device_resolution()

        # Connect to ReachyMini
        try:
            logger.info("Attempting to connect to Reachy Mini...")
            super().wrapped_run(*args, **kwargs)
        except TimeoutError as e:
            logger.error(f"Timeout connecting to Reachy Mini: {e}")
            sys.exit(1)
        except Exception as e:
            error_str = str(e)
            if "Unable to connect" in error_str or "Timeout" in error_str:
                logger.error(f"Failed to connect to Reachy Mini: {e}")
                sys.exit(1)
            else:
                raise

    def run(self, reachy_mini, stop_event: threading.Event) -> None:
        """
        Main application entry point.

        Args:
            reachy_mini: The Reachy Mini robot instance (required, cannot be None)
            stop_event: Event to signal graceful shutdown
        """
        logger.info("Starting Reachy Mini for Home Assistant...")

        # Optional health/memory monitors
        enable_monitors = os.environ.get("REACHY_ENABLE_FRAMEWORK_MONITORS", "1").lower() in ("1", "true", "yes", "on")
        health_monitor = get_health_monitor() if enable_monitors else None
        memory_monitor = get_memory_monitor() if enable_monitors else None

        # Create and run the HA service
        service = VoiceAssistantService(reachy_mini)

        if enable_monitors:
            health_monitor.register_checker(
                "voice_assistant",
                lambda: service.is_running if hasattr(service, "is_running") else True,
                interval=30.0,
            )

        # Always create a new event loop to avoid conflicts with SDK
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug("Created new event loop for HA service")

        try:
            if enable_monitors:
                health_monitor.start()
                memory_monitor.start()

            loop.run_until_complete(service.start())

            logger.info("=" * 50)
            logger.info("Reachy Mini for Home Assistant Started!")
            logger.info("=" * 50)
            logger.info("ESPHome Server: 0.0.0.0:6053")
            logger.info("Camera Server: 0.0.0.0:8081")
            logger.info("Wake word: Okay Nabu")
            logger.info("Motion control: enabled")
            logger.info("Camera: enabled (Reachy Mini)")
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

            if enable_monitors:
                health_monitor.stop()
                memory_monitor.stop()

            # Note: Robot connection cleanup is handled by SDK's context manager
            # in wrapped_run(). We only need to close our event loop here.

            # Close event loop
            try:
                loop.close()
            except Exception as e:
                logger.debug(f"Error closing event loop: {e}")

            logger.info("Reachy Mini HA stopped.")


# This is called when running as: python -m reachy_mini_home_assistant.main
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Reduce verbosity for some noisy modules
    logging.getLogger("reachy_mini.media.media_manager").setLevel(logging.WARNING)
    logging.getLogger("reachy_mini.media.camera_base").setLevel(logging.WARNING)
    logging.getLogger("reachy_mini.media.audio_base").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    app = ReachyMiniHaVoice()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
