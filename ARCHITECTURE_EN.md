# Reachy Mini Home Assistant Voice Assistant - Architecture Design

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Application Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Home         │  │ Web UI       │  │ Console      │           │
│  │ Assistant    │  │ (Gradio)     │  │ Interface    │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Business Logic Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Voice        │  │ Motion       │  │ State        │           │
│  │ Manager      │  │ Controller   │  │ Manager      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ ESPHome      │  │ Event        │                           │
│  │ Handler      │  │ Dispatcher   │                           │
│  └──────────────┘  └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                        Services Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Wake Word    │  │ Audio        │  │ Motion       │           │
│  │ Detector     │  │ Processor    │  │ Queue        │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────────────────────────────────────────────┐       │
│  │ ESPHome Protocol (Audio Streaming to/from HA)       │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Hardware Abstraction Layer                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Audio        │  │ Motion       │  │ Camera       │           │
│  │ Adapter      │  │ Adapter      │  │ Adapter      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ Reachy Mini  │  │ ESPHome      │                           │
│  │ SDK Wrapper  │  │ Protocol     │                           │
│  └──────────────┘  └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│           Reachy Mini Hardware + Home Assistant                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Microphone   │  │ Head Motors  │  │ Camera       │           │
│  │ Array (4)    │  │ (6 DOF)      │  │ (Wide)       │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │ Speaker      │  │ Antennas     │                           │
│  │ (5W)         │  │ (2)          │                           │
│  └──────────────┘  └──────────────┘                           │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Home Assistant (STT/TTS Processing)                 │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Core Design Principles

### 2.1 Based on linux-voice-assistant
This project is based on the architecture of [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant), with key features:

- **STT/TTS Handled by Home Assistant**: Audio data is transmitted to Home Assistant via ESPHome protocol for speech recognition and synthesis
- **Local Wake Word Detection**: Uses microWakeWord or openWakeWord for offline wake word detection
- **ESPHome Protocol Communication**: Communicates with Home Assistant via ESPHome protocol
- **Motion Control Enhancement**: Integrates Reachy Mini's motion control capabilities

### 2.2 Architecture Characteristics
- **Modular Design**: Audio, voice, motion, and ESPHome modules are independent
- **Asynchronous Processing**: Uses asyncio for high-performance asynchronous processing
- **State Management**: Centralized state management (ServerState)
- **Event-Driven**: Event-based communication mechanism

## 3. Module Design

### 3.1 Audio Module (audio/)

**Responsibilities**:
- Audio device management (microphone, speaker)
- Audio recording and playback
- Audio format conversion (16KHz mono PCM)

**Interfaces**:

```python
class AudioAdapter(ABC):
    """Audio device adapter abstract base class"""
    
    @abstractmethod
    async def list_input_devices(self) -> List[AudioDevice]:
        """List available audio input devices"""
        pass
    
    @abstractmethod
    async def list_output_devices(self) -> List[AudioDevice]:
        """List available audio output devices"""
        pass
    
    @abstractmethod
    async def start_recording(self, device: str, callback: Callable) -> None:
        """Start audio recording"""
        pass
    
    @abstractmethod
    async def stop_recording(self) -> None:
        """Stop audio recording"""
        pass
    
    @abstractmethod
    async def play_audio(self, audio_data: bytes, device: str) -> None:
        """Play audio"""
        pass
```

**Key Components**:
- `adapter.py`: Audio device adapter implementation
- `processor.py`: Audio processor (format conversion, buffering)

### 3.2 Voice Module (voice/)

**Responsibilities**:
- Wake word detection (local offline)
- STT (Speech-to-Text) - backup implementation
- TTS (Text-to-Speech) - backup implementation

**Interfaces**:

```python
class WakeWordDetector(ABC):
    """Wake word detector abstract base class"""
    
    @abstractmethod
    async def load_model(self, model_path: str) -> None:
        """Load wake word model"""
        pass
    
    @abstractmethod
    async def detect(self, audio_chunk: bytes) -> bool:
        """Detect wake word in audio chunk"""
        pass
    
    @abstractmethod
    async def set_sensitivity(self, sensitivity: float) -> None:
        """Set detection sensitivity"""
        pass
```

**Key Components**:
- `detector.py`: Wake word detector (microWakeWord/openWakeWord)
- `stt.py`: STT engine (Whisper - backup)
- `tts.py`: TTS engine (Piper - backup)

### 3.3 Motion Module (motion/)

**Responsibilities**:
- Head motion control (6 DOF)
- Antenna animation
- Motion queue management (priority-based)
- Speech-reactive motions

**Interfaces**:

```python
class MotionController(ABC):
    """Motion controller abstract base class"""
    
    @abstractmethod
    async def connect(self, host: str, wireless: bool) -> None:
        """Connect to Reachy Mini"""
        pass
    
    @abstractmethod
    async def move_head(self, pose: HeadPose, duration: float) -> None:
        """Move head to specified pose"""
        pass
    
    @abstractmethod
    async def set_antenna(self, antenna_id: int, angle: float) -> None:
        """Set antenna angle"""
        pass
    
    @abstractmethod
    async def play_emotion(self, emotion: str) -> None:
        """Play emotion"""
        pass
```

**Key Components**:
- `controller.py`: Motion controller implementation
- `queue.py`: Motion queue manager (priority-based)

### 3.4 ESPHome Module (esphome/)

**Responsibilities**:
- ESPHome protocol server implementation
- Audio streaming to/from Home Assistant
- Event handling (wake word, TTS start/end, STT result)
- mDNS service discovery

**Interfaces**:

```python
class ESPHomeServer(ABC):
    """ESPHome server abstract base class"""
    
    @abstractmethod
    async def start(self, host: str, port: int) -> None:
        """Start ESPHome server"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop ESPHome server"""
        pass
    
    @abstractmethod
    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio to Home Assistant"""
        pass
    
    @abstractmethod
    async def on_event(self, event: ESPHomeEvent) -> None:
        """Handle ESPHome event"""
        pass
```

**Key Components**:
- `protocol.py`: ESPHome protocol definitions
- `server.py`: ESPHome server implementation

### 3.5 Configuration Module (config/)

**Responsibilities**:
- Configuration file management
- Environment variable management
- Default configuration

**Interfaces**:

```python
class ConfigManager:
    """Configuration manager"""
    
    def __init__(self, config_path: str):
        """Initialize configuration manager"""
        pass
    
    def load(self) -> Dict:
        """Load configuration"""
        pass
    
    def save(self, config: Dict) -> None:
        """Save configuration"""
        pass
    
    def get(self, key: str, default=None) -> Any:
        """Get configuration value"""
        pass
```

**Key Components**:
- `manager.py`: Configuration manager implementation

## 4. Data Flow

### 4.1 Wake Word Detection Flow

```
Microphone Input (16kHz PCM)
    ↓
Audio Chunk (1024 samples)
    ↓
Wake Word Detector
    ├─ microWakeWord Features
    └─ openWakeWord Features
    ↓
Detection
    ├─ microWakeWord: probability > cutoff
    └─ openWakeWord: probability > 0.5
    ↓
Refractory Period Check (2 seconds)
    ↓
Trigger Wakeup Event
    ↓
ESPHome Server → Home Assistant
```

### 4.2 Audio Streaming Flow (to Home Assistant)

```
Microphone Input
    ↓
Audio Chunk
    ↓
ESPHome Server
    ↓
VoiceAssistantAudio Message
    ↓
Home Assistant (STT Processing)
    ↓
VoiceAssistantEvent (STT Result)
```

### 4.3 TTS Audio Flow (from Home Assistant)

```
Home Assistant (TTS Processing)
    ↓
VoiceAssistantEvent (TTS Start)
    ↓
ESPHome Server
    ↓
Motion Controller (Speech-reactive motions)
    ↓
VoiceAssistantAudio (TTS Audio)
    ↓
Speaker Playback
    ↓
VoiceAssistantEvent (TTS End)
```

## 5. State Management

### 5.1 ServerState

Centralized state management:

```python
class ServerState:
    """Server global state"""
    
    # Application info
    name: str
    mac_address: str
    
    # Audio
    audio_queue: Queue
    audio_input_device: Optional[str]
    audio_output_device: Optional[str]
    
    # Voice
    wake_words: Dict[str, WakeWordDetector]
    active_wake_words: List[str]
    stop_word: WakeWordDetector
    
    # Motion
    motion_controller: MotionController
    motion_queue: MotionQueue
    
    # ESPHome
    esphome_server: ESPHomeServer
    esphome_connected: bool
    
    # Status
    is_streaming_audio: bool
    is_playing_tts: bool
```

## 6. Deployment Architecture

### 6.1 Running on Reachy Mini

```
Reachy Mini (Raspberry Pi 4)
├── Application (This Project)
│   ├── Audio Module
│   ├── Voice Module
│   ├── Motion Module
│   └── ESPHome Module
├── Reachy Mini Hardware
│   ├── 4 Microphones
│   ├── 5W Speaker
│   ├── Head Motors (6 DOF)
│   └── Antennas (2)
└── Network
    └── ESPHome Protocol (Port 6053)
        └→ Home Assistant
```

### 6.2 Home Assistant Integration

```
Home Assistant
├── ESPHome Integration
│   └→ Reachy Mini (ESPHome Server)
├── Voice Assistant
│   ├── STT Service
│   └── TTS Service
└── Automations
    └→ Voice Commands
```

## 7. Performance Considerations

### 7.1 Latency Targets

- **Wake Word Detection**: < 500ms
- **Audio Streaming**: < 100ms
- **TTS Playback**: < 200ms
- **Motion Response**: < 100ms

### 7.2 Resource Requirements

- **CPU**: Raspberry Pi 4 (4 cores)
- **RAM**: 4GB minimum
- **Network**: Stable WiFi/Ethernet connection

## 8. Security Considerations

### 8.1 ESPHome Security

- Use encrypted connections (TLS)
- Implement authentication (if required)
- Validate all incoming messages

### 8.2 Audio Privacy

- Audio data is transmitted only when wake word is detected
- Support for local-only mode (no audio transmission)
- Clear audio recording indicators

## 9. Future Extensions

### 9.1 Additional Features

- Face tracking (camera integration)
- Visual recognition (SmolVLM2)
- Advanced emotions (dance library)
- Multi-language support

### 9.2 Performance Optimizations

- GPU acceleration for wake word detection
- Audio preprocessing on hardware
- Motion trajectory optimization

---

**Note**: This architecture document is the English version of ARCHITECTURE.md. For the Chinese version, see ARCHITECTURE.md.