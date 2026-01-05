#!/usr/bin/env python3
"""Main entry point for Reachy Mini Home Assistant Voice Assistant.

This module provides a command-line interface for running the voice assistant
in standalone mode (without the ReachyMini App framework).
"""

import argparse
import asyncio
import logging
import threading

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reachy Mini Home Assistant Voice Assistant"
    )
    parser.add_argument(
        "--name",
        default="Reachy Mini",
        help="Name of the voice assistant (default: Reachy Mini)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Address for ESPHome server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=6053,
        help="Port for ESPHome server (default: 6053)",
    )
    parser.add_argument(
        "--wake-model",
        default="okay_nabu",
        help="Id of active wake model (default: okay_nabu)",
    )
    parser.add_argument(
        "--camera-port",
        type=int,
        default=8081,
        help="Port for camera server (default: 8081)",
    )
    parser.add_argument(
        "--no-camera",
        action="store_true",
        help="Disable camera server",
    )
    parser.add_argument(
        "--no-motion",
        action="store_true",
        help="Disable Reachy Mini motion control",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print DEBUG messages to console",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize Reachy Mini (if available)
    reachy_mini = None
    if not args.no_motion:
        try:
            from reachy_mini import ReachyMini
            reachy_mini = ReachyMini()
            _LOGGER.info("Reachy Mini connected")
        except ImportError:
            _LOGGER.warning("reachy-mini not installed, motion control disabled")
        except Exception as e:
            _LOGGER.warning("Failed to connect to Reachy Mini: %s", e)

    # Import and create VoiceAssistantService
    from .voice_assistant import VoiceAssistantService

    service = VoiceAssistantService(
        reachy_mini=reachy_mini,
        name=args.name,
        host=args.host,
        port=args.port,
        wake_model=args.wake_model,
        camera_port=args.camera_port,
        camera_enabled=not args.no_camera,
    )

    # Create stop event for graceful shutdown
    stop_event = threading.Event()

    try:
        await service.start()

        _LOGGER.info("=" * 50)
        _LOGGER.info("Reachy Mini Voice Assistant Started")
        _LOGGER.info("=" * 50)
        _LOGGER.info("Name: %s", args.name)
        _LOGGER.info("ESPHome Server: %s:%s", args.host, args.port)
        _LOGGER.info("Camera Server: %s:%s", args.host, args.camera_port)
        _LOGGER.info("Motion control: %s", "enabled" if reachy_mini else "disabled")
        _LOGGER.info("=" * 50)
        _LOGGER.info("Add this device in Home Assistant:")
        _LOGGER.info("  Settings -> Devices & Services -> Add Integration -> ESPHome")
        _LOGGER.info("  Enter: <this-device-ip>:%s", args.port)
        _LOGGER.info("=" * 50)

        # Wait for stop signal
        while not stop_event.is_set():
            await asyncio.sleep(0.5)

    except KeyboardInterrupt:
        _LOGGER.info("Shutting down...")
    finally:
        await service.stop()
        _LOGGER.info("Voice assistant stopped")


def run():
    """Entry point for the application."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
