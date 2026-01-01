"""
Motion queue for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class MotionPriority(Enum):
    """Motion priority levels"""
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class Motion:
    """Motion command"""
    name: str
    execute: callable
    priority: MotionPriority = MotionPriority.MEDIUM
    duration: float = 1.0


class MotionQueue:
    """Motion queue manager"""
    
    def __init__(self):
        self.high_priority = asyncio.Queue()
        self.medium_priority = asyncio.Queue()
        self.low_priority = asyncio.Queue()
        self.is_running = False
        self._current_motion: Optional[Motion] = None
        self._task: Optional[asyncio.Task] = None
    
    async def add_motion(self, motion: Motion):
        """Add motion to queue based on priority"""
        if motion.priority == MotionPriority.HIGH:
            await self.high_priority.put(motion)
        elif motion.priority == MotionPriority.MEDIUM:
            await self.medium_priority.put(motion)
        elif motion.priority == MotionPriority.LOW:
            await self.low_priority.put(motion)
        else:
            logger.warning(f"Unknown priority: {motion.priority}")
            return
        
        logger.debug(f"Added motion '{motion.name}' to queue (priority: {motion.priority.name})")
    
    async def add_high_priority(self, name: str, execute: callable, duration: float = 1.0):
        """Add high priority motion"""
        motion = Motion(name, execute, MotionPriority.HIGH, duration)
        await self.add_motion(motion)
    
    async def add_medium_priority(self, name: str, execute: callable, duration: float = 1.0):
        """Add medium priority motion"""
        motion = Motion(name, execute, MotionPriority.MEDIUM, duration)
        await self.add_motion(motion)
    
    async def add_low_priority(self, name: str, execute: callable, duration: float = 1.0):
        """Add low priority motion"""
        motion = Motion(name, execute, MotionPriority.LOW, duration)
        await self.add_motion(motion)
    
    async def start(self):
        """Start processing motion queue"""
        if self.is_running:
            logger.warning("Motion queue already running")
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("Started motion queue")
    
    async def stop(self):
        """Stop processing motion queue"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped motion queue")
    
    async def clear(self):
        """Clear all queues"""
        while not self.high_priority.empty():
            await self.high_priority.get()
        while not self.medium_priority.empty():
            await self.medium_priority.get()
        while not self.low_priority.empty():
            await self.low_priority.get()
        logger.info("Cleared motion queues")
    
    async def _process_queue(self):
        """Process motion queue"""
        try:
            while self.is_running:
                # Get next motion based on priority
                motion = await self._get_next_motion()
                
                if motion is None:
                    await asyncio.sleep(0.01)
                    continue
                
                # Execute motion
                self._current_motion = motion
                logger.info(f"Executing motion: {motion.name}")
                
                try:
                    await motion.execute()
                except Exception as e:
                    logger.error(f"Error executing motion '{motion.name}': {e}")
                finally:
                    self._current_motion = None
        except asyncio.CancelledError:
            logger.debug("Motion queue processing cancelled")
        except Exception as e:
            logger.error(f"Error in motion queue processing: {e}")
    
    async def _get_next_motion(self) -> Optional[Motion]:
        """Get next motion based on priority"""
        # Priority: HIGH > MEDIUM > LOW
        if not self.high_priority.empty():
            return await self.high_priority.get()
        elif not self.medium_priority.empty():
            return await self.medium_priority.get()
        elif not self.low_priority.empty():
            return await self.low_priority.get()
        else:
            return None
    
    def is_empty(self) -> bool:
        """Check if all queues are empty"""
        return (
            self.high_priority.empty() and
            self.medium_priority.empty() and
            self.low_priority.empty()
        )
    
    def get_queue_size(self) -> dict:
        """Get size of each queue"""
        return {
            "high": self.high_priority.qsize(),
            "medium": self.medium_priority.qsize(),
            "low": self.low_priority.qsize()
        }
    
    def get_current_motion(self) -> Optional[Motion]:
        """Get currently executing motion"""
        return self._current_motion