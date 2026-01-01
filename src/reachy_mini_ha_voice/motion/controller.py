"""
Motion controller for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np
from scipy.spatial.transform import Rotation as R

logger = logging.getLogger(__name__)


class MotionController(ABC):
    """Abstract base class for motion controller"""
    
    @abstractmethod
    async def connect(self, host: str = 'localhost'):
        """Connect to robot"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from robot"""
        pass
    
    @abstractmethod
    async def wake_up(self):
        """Wake up robot"""
        pass
    
    @abstractmethod
    async def turn_off(self):
        """Turn off robot"""
        pass
    
    @abstractmethod
    async def move_head(self, pose: np.ndarray, duration: float = 1.0):
        """Move head to pose"""
        pass
    
    @abstractmethod
    async def move_antennas(self, left: float, right: float, duration: float = 1.0):
        """Move antennas"""
        pass
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connected"""
        pass


class ReachyMiniMotionController(MotionController):
    """Reachy Mini motion controller"""
    
    def __init__(self):
        self.reachy_mini = None
        self._connected = False
        self._speech_reactive = False
        self._speech_task = None
    
    async def connect(self, host: str = 'localhost'):
        """Connect to Reachy Mini"""
        try:
            from reachy_mini import ReachyMini
            
            self.reachy_mini = ReachyMini(host=host)
            self._connected = True
            
            logger.info(f"Connected to Reachy Mini at {host}")
        except ImportError:
            logger.error("reachy-mini not installed. Install with: pip install reachy-mini")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Reachy Mini: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Reachy Mini"""
        if self.reachy_mini:
            try:
                await self.turn_off()
            except Exception as e:
                logger.error(f"Error turning off robot: {e}")
            finally:
                self.reachy_mini = None
                self._connected = False
                logger.info("Disconnected from Reachy Mini")
    
    async def wake_up(self):
        """Wake up robot"""
        if not self._connected or self.reachy_mini is None:
            logger.warning("Not connected to robot")
            return
        
        try:
            self.reachy_mini.wake_up()
            logger.info("Robot woke up")
        except Exception as e:
            logger.error(f"Failed to wake up robot: {e}")
            raise
    
    async def turn_off(self):
        """Turn off robot"""
        if not self._connected or self.reachy_mini is None:
            logger.warning("Not connected to robot")
            return
        
        try:
            self.reachy_mini.turn_off()
            logger.info("Robot turned off")
        except Exception as e:
            logger.error(f"Failed to turn off robot: {e}")
            raise
    
    async def move_head(self, pose: np.ndarray, duration: float = 1.0):
        """Move head to pose"""
        if not self._connected or self.reachy_mini is None:
            logger.warning("Not connected to robot")
            return
        
        try:
            self.reachy_mini.goto_target(head=pose, duration=duration)
            logger.debug(f"Moved head (duration: {duration}s)")
        except Exception as e:
            logger.error(f"Failed to move head: {e}")
            raise
    
    async def move_antennas(self, left: float, right: float, duration: float = 1.0):
        """Move antennas"""
        if not self._connected or self.reachy_mini is None:
            logger.warning("Not connected to robot")
            return
        
        try:
            self.reachy_mini.goto_target(antennas=[left, right], duration=duration)
            logger.debug(f"Moved antennas (left: {left}, right: {right})")
        except Exception as e:
            logger.error(f"Failed to move antennas: {e}")
            raise
    
    async def nod(self, count: int = 1, duration: float = 0.5):
        """Nod head"""
        for _ in range(count):
            # Nod down
            pose_down = np.eye(4)
            pose_down[:3, :3] = R.from_euler('xyz', [15, 0, 0], degrees=True).as_matrix()
            await self.move_head(pose_down, duration=duration / 2)
            
            # Nod up
            pose_up = np.eye(4)
            pose_up[:3, :3] = R.from_euler('xyz', [-15, 0, 0], degrees=True).as_matrix()
            await self.move_head(pose_up, duration=duration / 2)
    
    async def shake(self, count: int = 1, duration: float = 0.5):
        """Shake head"""
        for _ in range(count):
            # Shake left
            pose_left = np.eye(4)
            pose_left[:3, :3] = R.from_euler('xyz', [0, 0, -20], degrees=True).as_matrix()
            await self.move_head(pose_left, duration=duration / 2)
            
            # Shake right
            pose_right = np.eye(4)
            pose_right[:3, :3] = R.from_euler('xyz', [0, 0, 20], degrees=True).as_matrix()
            await self.move_head(pose_right, duration=duration / 2)
    
    async def look_at(self, x: float = 0.5, y: float = 0.0, z: float = 0.0, duration: float = 1.0):
        """Look at a point"""
        # Calculate yaw and pitch
        yaw = np.arctan2(x, z)
        pitch = np.arctan2(y, np.sqrt(x**2 + z**2))
        
        # Create pose
        pose = np.eye(4)
        pose[:3, :3] = R.from_euler('xyz', [pitch, 0, yaw], degrees=True).as_matrix()
        
        await self.move_head(pose, duration=duration)
    
    async def start_speech_reactive_motion(self):
        """Start speech reactive motion"""
        if self._speech_reactive:
            return
        
        self._speech_reactive = True
        self._speech_task = asyncio.create_task(self._speech_reactive_loop())
        logger.info("Started speech reactive motion")
    
    async def stop_speech_reactive_motion(self):
        """Stop speech reactive motion"""
        if not self._speech_reactive:
            return
        
        self._speech_reactive = False
        if self._speech_task:
            self._speech_task.cancel()
            try:
                await self._speech_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped speech reactive motion")
    
    async def _speech_reactive_loop(self):
        """Speech reactive motion loop"""
        try:
            while self._speech_reactive:
                # Generate subtle wobble
                roll = np.sin(asyncio.get_event_loop().time() * 2) * 3
                pose = np.eye(4)
                pose[:3, :3] = R.from_euler('xyz', [0, 0, roll], degrees=True).as_matrix()
                
                await self.move_head(pose, duration=0.1)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.debug("Speech reactive loop cancelled")
        except Exception as e:
            logger.error(f"Error in speech reactive loop: {e}")
    
    async def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected


class MockMotionController(MotionController):
    """Mock motion controller for testing"""
    
    def __init__(self):
        self._connected = False
    
    async def connect(self, host: str = 'localhost'):
        """Connect to mock robot"""
        self._connected = True
        logger.info("Connected to mock robot")
    
    async def disconnect(self):
        """Disconnect from mock robot"""
        self._connected = False
        logger.info("Disconnected from mock robot")
    
    async def wake_up(self):
        """Wake up mock robot"""
        logger.info("Mock robot woke up")
    
    async def turn_off(self):
        """Turn off mock robot"""
        logger.info("Mock robot turned off")
    
    async def move_head(self, pose: np.ndarray, duration: float = 1.0):
        """Move mock head"""
        logger.debug(f"Mock head moved (duration: {duration}s)")
        await asyncio.sleep(duration)
    
    async def move_antennas(self, left: float, right: float, duration: float = 1.0):
        """Move mock antennas"""
        logger.debug(f"Mock antennas moved (left: {left}, right: {right})")
        await asyncio.sleep(duration)
    
    async def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected