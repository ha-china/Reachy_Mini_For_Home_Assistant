"""
Reachy Mini Home Assistant Voice Assistant App

This app integrates Reachy Mini with Home Assistant via ESPHome protocol,
allowing voice control through Home Assistant's voice assistant pipeline.
"""

import threading
import logging
import asyncio
from typing import Optional

from reachy_mini import ReachyMini
from reachy_mini.apps import ReachyMiniApp

from reachy_mini_ha_voice.voice_assistant import VoiceAssistantService

logger = logging.getLogger(__name__)


class HomeAssistantVoiceApp(ReachyMiniApp):
    """
    Reachy Mini Home Assistant Voice Assistant Application.

    This app runs an ESPHome-compatible voice satellite that connects
    to Home Assistant for STT/TTS processing while providing local
    wake word detection and robot motion feedback.
    """

    # No custom web UI needed - configuration is automatic
    custom_app_url: Optional[str] = None

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        """
        Main application entry point.

        Args:
            reachy_mini: The Reachy Mini robot instance
            stop_event: Event to signal graceful shutdown
        """
        logger.info("Starting Home Assistant Voice Assistant...")

        # Create and run the voice assistant service
        service = VoiceAssistantService(reachy_mini)

        # Run the async service in an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(service.start())

            logger.info("=" * 50)
            logger.info("Home Assistant Voice Assistant Started!")
            logger.info("=" * 50)
            logger.info("ESPHome Server: 0.0.0.0:6053")
            logger.info("Wake word: Okay Nabu")
            logger.info("=" * 50)
            logger.info("To connect from Home Assistant:")
            logger.info("  Settings -> Devices & Services -> Add Integration")
            logger.info("  -> ESPHome -> Enter this device's IP:6053")
            logger.info("=" * 50)

            # Wait for stop signal
            while not stop_event.is_set():
                loop.run_until_complete(asyncio.sleep(0.5))

        except Exception as e:
            logger.error(f"Error running voice assistant: {e}")
            raise
        finally:
            logger.info("Shutting down voice assistant...")
            loop.run_until_complete(service.stop())
            loop.close()
            logger.info("Voice assistant stopped.")


# Entry point for the app
App = HomeAssistantVoiceApp
