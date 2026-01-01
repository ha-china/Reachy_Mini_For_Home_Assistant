"""
Audio device adapter for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional
import sounddevice as sd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Audio device information"""
    index: int
    name: str
    sample_rate: int
    channels: int
    is_input: bool
    is_output: bool


class AudioAdapter(ABC):
    """Abstract base class for audio device adapter"""
    
    @abstractmethod
    async def list_input_devices(self) -> List[AudioDevice]:
        """List available audio input devices"""
        pass
    
    @abstractmethod
    async def list_output_devices(self) -> List[AudioDevice]:
        """List available audio output devices"""
        pass
    
    @abstractmethod
    async def start_recording(
        self,
        device_id: Optional[str],
        callback: Callable[[bytes], None],
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 1024
    ):
        """Start recording audio"""
        pass
    
    @abstractmethod
    async def stop_recording(self):
        """Stop recording audio"""
        pass
    
    @abstractmethod
    async def play_audio(
        self,
        audio_data: bytes,
        device_id: Optional[str],
        sample_rate: int = 16000,
        channels: int = 1
    ):
        """Play audio"""
        pass


class MicrophoneArray(AudioAdapter):
    """Microphone array adapter for Reachy Mini"""
    
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream = None
        self._is_recording = False
        self._callback = None
        self._loop = None
    
    async def list_input_devices(self) -> List[AudioDevice]:
        """List available audio input devices"""
        devices = []
        for i, device in enumerate(sd.query_devices()):
            if device['max_input_channels'] > 0:
                devices.append(AudioDevice(
                    index=i,
                    name=device['name'],
                    sample_rate=int(device['default_samplerate']),
                    channels=device['max_input_channels'],
                    is_input=True,
                    is_output=False
                ))
        return devices
    
    async def list_output_devices(self) -> List[AudioDevice]:
        """List available audio output devices"""
        devices = []
        for i, device in enumerate(sd.query_devices()):
            if device['max_output_channels'] > 0:
                devices.append(AudioDevice(
                    index=i,
                    name=device['name'],
                    sample_rate=int(device['default_samplerate']),
                    channels=device['max_output_channels'],
                    is_input=False,
                    is_output=True
                ))
        return devices
    
    async def start_recording(
        self,
        device_id: Optional[str],
        callback: Callable[[bytes], None],
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 1024
    ):
        """Start recording from microphone"""
        if self._is_recording:
            logger.warning("Already recording")
            return
        
        self._callback = callback
        self._loop = asyncio.get_event_loop()
        self._is_recording = True
        
        def audio_callback(indata, frames, time, status):
            """Callback for audio stream"""
            if status:
                logger.warning(f"Audio callback status: {status}")
            
            if not self._is_recording:
                return
            
            # Convert to 16-bit PCM
            audio_data = (
                (np.clip(indata, -1.0, 1.0) * 32767.0)
                .astype("<i2")
                .tobytes()
            )
            
            # Call the callback in the event loop
            if self._loop and self._callback:
                self._loop.call_soon_threadsafe(self._callback, audio_data)
        
        try:
            self._stream = sd.InputStream(
                device=device_id,
                samplerate=sample_rate,
                channels=channels,
                blocksize=block_size,
                callback=audio_callback,
                dtype='float32'
            )
            self._stream.start()
            logger.info(f"Started recording from device: {device_id or 'default'}")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self._is_recording = False
            raise
    
    async def stop_recording(self):
        """Stop recording"""
        if not self._is_recording:
            return
        
        self._is_recording = False
        
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
                logger.info("Stopped recording")
            except Exception as e:
                logger.error(f"Failed to stop recording: {e}")
            finally:
                self._stream = None
        
        self._callback = None
        self._loop = None


class Speaker(AudioAdapter):
    """Speaker adapter for Reachy Mini"""
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._stream = None
        self._is_playing = False
    
    async def list_input_devices(self) -> List[AudioDevice]:
        """List available audio input devices (not applicable for speaker)"""
        return []
    
    async def list_output_devices(self) -> List[AudioDevice]:
        """List available audio output devices"""
        devices = []
        for i, device in enumerate(sd.query_devices()):
            if device['max_output_channels'] > 0:
                devices.append(AudioDevice(
                    index=i,
                    name=device['name'],
                    sample_rate=int(device['default_samplerate']),
                    channels=device['max_output_channels'],
                    is_input=False,
                    is_output=True
                ))
        return devices
    
    async def start_recording(
        self,
        device_id: Optional[str],
        callback: Callable[[bytes], None],
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 1024
    ):
        """Start recording (not applicable for speaker)"""
        raise NotImplementedError("Speaker does not support recording")
    
    async def stop_recording(self):
        """Stop recording (not applicable for speaker)"""
        raise NotImplementedError("Speaker does not support recording")
    
    async def play_audio(
        self,
        audio_data: bytes,
        device_id: Optional[str],
        sample_rate: int = 16000,
        channels: int = 1
    ):
        """Play audio to speaker"""
        try:
            # Convert from 16-bit PCM to float32
            audio_array = np.frombuffer(audio_data, dtype="<i2").astype(np.float32) / 32768.0
            
            # Play audio
            sd.play(audio_array, samplerate=sample_rate, device=device_id)
            sd.wait()
            logger.debug("Audio playback completed")
        except Exception as e:
            logger.error(f"Failed to play audio: {e}")
            raise


async def list_audio_devices():
    """List all available audio devices"""
    microphone = MicrophoneArray()
    
    print("\n=== Audio Input Devices ===")
    input_devices = await microphone.list_input_devices()
    for device in input_devices:
        print(f"{device.index}: {device.name} ({device.sample_rate}Hz, {device.channels}ch)")
    
    print("\n=== Audio Output Devices ===")
    output_devices = await microphone.list_output_devices()
    for device in output_devices:
        print(f"{device.index}: {device.name} ({device.sample_rate}Hz, {device.channels}ch)")
    
    print()