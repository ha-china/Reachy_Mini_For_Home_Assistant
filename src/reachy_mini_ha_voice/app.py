"""
Main application for Reachy Mini Home Assistant Voice Assistant
"""

import asyncio
import logging
import threading
from typing import Optional

from reachy_mini import ReachyMini, ReachyMiniApp

from .config.manager import ConfigManager
from .audio.adapter import MicrophoneArray, Speaker
from .audio.processor import AudioProcessor
from .voice.detector import WakeWordDetector, load_wake_word_detector
from .motion.controller import MotionController, ReachyMiniMotionController, MockMotionController
from .motion.queue import MotionQueue, MotionPriority
from .esphome.server import ESPHomeServer, VoiceSatelliteProtocol

logger = logging.getLogger(__name__)


class ServerState:
    """Global server state"""
    
    def __init__(self, name: str):
        self.name = name
        self.config = None
        self.microphone = None
        self.speaker = None
        self.audio_processor = None
        self.wake_word_detector = None
        self.motion_controller = None
        self.motion_queue = None
        self.esphome_server = None
        self.voice_satellite = None
        self._is_running = False
    
    async def initialize(self, config: ConfigManager):
        """Initialize all components"""
        self.config = config
        
        # Initialize audio
        self.microphone = MicrophoneArray(
            sample_rate=config.get("audio.sample_rate", 16000),
            channels=config.get("audio.channels", 1)
        )
        self.speaker = Speaker(
            sample_rate=config.get("audio.sample_rate", 16000)
        )
        
        # Initialize audio processor
        self.audio_processor = AudioProcessor(
            sample_rate=config.get("audio.sample_rate", 16000),
            channels=config.get("audio.channels", 1),
            block_size=config.get("audio.block_size", 1024)
        )
        
        # Initialize wake word detector
        wake_word_model = config.get("voice.wake_word", "okay_nabu")
        self.wake_word_detector = await load_wake_word_detector(
            f"wakewords/{wake_word_model}.tflite",
            detector_type="micro"
        )
        
        # Initialize motion controller
        robot_host = config.get("robot.host", "localhost")
        if robot_host == "mock":
            self.motion_controller = MockMotionController()
        else:
            self.motion_controller = ReachyMiniMotionController()
        
        await self.motion_controller.connect(robot_host)
        await self.motion_controller.wake_up()
        
        # Initialize motion queue
        self.motion_queue = MotionQueue()
        await self.motion_queue.start()
        
        # Initialize ESPHome server
        esphome_host = config.get("esphome.host", "0.0.0.0")
        esphome_port = config.get("esphome.port", 6053)
        self.esphome_server = ESPHomeServer(esphome_host, esphome_port)
        
        # Initialize voice satellite protocol
        self.voice_satellite = VoiceSatelliteProtocol(self)
        
        logger.info("Server state initialized")
    
    async def cleanup(self):
        """Cleanup all components"""
        if self.microphone:
            await self.microphone.stop_recording()
        
        if self.motion_controller:
            await self.motion_controller.stop_speech_reactive_motion()
            await self.motion_controller.turn_off()
            await self.motion_controller.disconnect()
        
        if self.motion_queue:
            await self.motion_queue.stop()
        
        if self.esphome_server:
            await self.esphome_server.stop()
        
        logger.info("Server state cleaned up")


class ReachyMiniVoiceApp(ReachyMiniApp):
    """Main application class for Reachy Mini Home Assistant Voice Assistant"""
    
    custom_app_url: Optional[str] = None  # Optional custom UI URL
    
    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        """
        Main entry point for the application
        
        Args:
            reachy_mini: Reachy Mini instance (already initialized and connected)
            stop_event: Threading event to signal graceful shutdown
        """
        logger.info("Starting Reachy Mini Home Assistant Voice Assistant")
        
        # Initialize configuration
        config = ConfigManager("config.json")
        
        # Create event loop for async operations
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create application instance
        app = ReachyMiniVoiceApp(
            name="Reachy Mini",
            config=config,
            robot_host="localhost",
            wireless=False
        )
        
        # Initialize state
        try:
            loop.run_until_complete(app.state.initialize(config))
            
            # Setup callbacks
            app._setup_callbacks()
            
            # Start audio recording
            loop.run_until_complete(app.state.microphone.start_recording(
                None,
                app._audio_callback,
                sample_rate=16000,
                channels=1,
                block_size=1024
            ))
            
            # Start ESPHome server
            loop.run_until_complete(app.state.esphome_server.start())
            
            # Register mDNS discovery
            loop.run_until_complete(app._register_mdns())
            
            logger.info("Application started successfully")
            
            # Main loop - check stop_event periodically
            while not stop_event.is_set():
                try:
                    loop.run_until_complete(asyncio.sleep(1))
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    break
            
        except Exception as e:
            logger.error(f"Error starting application: {e}", exc_info=True)
        finally:
            # Cleanup
            logger.info("Shutting down application...")
            loop.run_until_complete(app.state.cleanup())
            loop.close()
            logger.info("Application stopped")
    
    def _setup_callbacks(self):
        """Setup callbacks for audio processing"""
        # Add wake word callback
        self.state.audio_processor.add_wake_word_callback(self._on_audio_chunk)
        
        # Add stream callback
        self.state.audio_processor.add_stream_callback(self._on_stream_audio)
    
    async def _audio_callback(self, audio_chunk: bytes):
        """Callback for audio recording"""
        # Process audio chunk
        await self.state.audio_processor.process_audio_chunk(audio_chunk)
    
    async def _on_audio_chunk(self, audio_chunk: bytes):
        """Handle audio chunk for wake word detection"""
        if self.state.wake_word_detector:
            detected = await self.state.wake_word_detector.process_audio(audio_chunk)
            if detected:
                await self._on_wake_word_detected()
    
    async def _on_stream_audio(self, audio_chunk: bytes):
        """Handle audio chunk for streaming to Home Assistant"""
        if self.state.voice_satellite:
            await self.state.voice_satellite.handle_audio(audio_chunk)
    
    async def _on_wake_word_detected(self):
        """Handle wake word detection"""
        logger.info("Wake word detected!")
        
        # Nod to acknowledge
        if self.state.motion_controller:
            await self.state.motion_controller.nod(count=1, duration=0.3)
        
        # Trigger voice satellite
        if self.state.voice_satellite:
            await self.state.voice_satellite.handle_wake_word()
    
    async def _register_mdns(self):
        """Register mDNS service discovery"""
        try:
            from zeroconf import ServiceInfo, Zeroconf
            
            info = ServiceInfo(
                "_esphomelib._tcp.local.",
                f"{self.state.name}._esphomelib._tcp.local.",
                addresses=[],
                port=6053,
                properties={
                    "version": "1.0",
                    "name": self.state.name,
                    "platform": "reachy_mini"
                }
            )
            
            zeroconf = Zeroconf()
            zeroconf.register_service(info)
            
            logger.info(f"Registered mDNS service: {self.state.name}")
        except ImportError:
            logger.warning("zeroconf not installed, mDNS discovery not available")
        except Exception as e:
            logger.error(f"Failed to register mDNS service: {e}")
    
    async def handle_tts_audio(self, audio_data: bytes):
        """Handle TTS audio from Home Assistant"""
        logger.info("Received TTS audio from Home Assistant")
        
        # Play audio
        if self.state.speaker:
            await self.state.speaker.play_audio(
                audio_data,
                None,
                sample_rate=16000,
                channels=1
            )
    
    async def handle_stt_result(self, text: str):
        """Handle STT result from Home Assistant"""
        logger.info(f"Received STT result: {text}")
        
        # Process text (add custom logic here)
        if "你好" in text or "hello" in text.lower():
            await self._say_hello()
        elif "跳舞" in text or "dance" in text.lower():
            await self._dance()
    
    async def _say_hello(self):
        """Say hello with motion"""
        if self.state.motion_controller:
            # Nod
            await self.state.motion_controller.nod(count=2, duration=0.3)
            # Look up
            import numpy as np
            from scipy.spatial.transform import Rotation as R
            pose = np.eye(4)
            pose[:3, :3] = R.from_euler('xyz', [15, 0, 0], degrees=True).as_matrix()
            await self.state.motion_controller.move_head(pose, duration=0.5)
    
    async def _dance(self):
        """Perform a dance"""
        if self.state.motion_controller:
            # Simple dance: shake head
            await self.state.motion_controller.shake(count=3, duration=0.4)