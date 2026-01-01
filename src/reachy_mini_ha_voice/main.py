"""
Main entry point for Reachy Mini Home Assistant Voice Assistant
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .config.manager import ConfigManager
from .audio.adapter import AudioAdapter
from .voice.detector import WakeWordDetector
from .motion.controller import MotionController
from .esphome.server import ESPHomeServer
from .app import ReachyMiniVoiceApp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Reachy Mini Home Assistant Voice Assistant"
    )
    
    parser.add_argument(
        "--name",
        type=str,
        default="Reachy Mini",
        help="Name of the voice assistant (default: Reachy Mini)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to configuration file (default: config.json)"
    )
    
    parser.add_argument(
        "--audio-input-device",
        type=str,
        default=None,
        help="Audio input device name (default: auto-detect)"
    )
    
    parser.add_argument(
        "--audio-output-device",
        type=str,
        default=None,
        help="Audio output device name (default: auto-detect)"
    )
    
    parser.add_argument(
        "--list-input-devices",
        action="store_true",
        help="List available audio input devices and exit"
    )
    
    parser.add_argument(
        "--list-output-devices",
        action="store_true",
        help="List available audio output devices and exit"
    )
    
    parser.add_argument(
        "--wake-model",
        type=str,
        default="okay_nabu",
        help="Wake word model name (default: okay_nabu)"
    )
    
    parser.add_argument(
        "--wake-word-dir",
        type=str,
        action="append",
        help="Additional wake word directory (can be used multiple times)"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="ESPHome server host (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=6053,
        help="ESPHome server port (default: 6053)"
    )
    
    parser.add_argument(
        "--robot-host",
        type=str,
        default="localhost",
        help="Reachy Mini robot host (default: localhost)"
    )
    
    parser.add_argument(
        "--wireless",
        action="store_true",
        help="Use wireless version of Reachy Mini"
    )
    
    parser.add_argument(
        "--gradio",
        action="store_true",
        help="Launch Gradio web UI"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    return parser.parse_args()


async def list_audio_devices():
    """List available audio devices"""
    import sounddevice as sd
    
    print("\n=== Audio Input Devices ===")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"{i}: {device['name']}")
    
    print("\n=== Audio Output Devices ===")
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:
            print(f"{i}: {device['name']}")
    
    print()


async def main():
    """Main entry point"""
    args = parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # List audio devices if requested
    if args.list_input_devices or args.list_output_devices:
        await list_audio_devices()
        return
    
    # Load configuration
    config = ConfigManager(args.config)
    logger.info(f"Loaded configuration from {args.config}")
    
    # Create application
    app = ReachyMiniVoiceApp(
        name=args.name,
        config=config,
        audio_input_device=args.audio_input_device,
        audio_output_device=args.audio_output_device,
        wake_model=args.wake_model,
        wake_word_dirs=args.wake_word_dir,
        host=args.host,
        port=args.port,
        robot_host=args.robot_host,
        wireless=args.wireless,
        gradio=args.gradio
    )
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(app.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start application
    try:
        await app.start()
    except Exception as e:
        logger.error(f"Error starting application: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())