# Reachy Mini Home Assistant Voice Assistant Project Plan

## 📋 Reference Resources Analysis

### 1. OHF-Voice/linux-voice-assistant
- **Core Features**: Home Assistant voice assistant based on ESPHome protocol
- **Key Components**:
  - Wake word detection (microWakeWord/openWakeWord)
  - Speech-to-Text (STT)
  - Text-to-Speech (TTS)
  - ESPHome protocol communication (port 6053)
  - Audio processing (16KHz mono microphone)
- **Tech Stack**: Python 3.11/3.13, ESPHome, PulseAudio

### 2. Reachy Mini SDK
- **Hardware Capabilities**: 4 microphones, 5W speaker, wide-angle camera, 6-DOF head movement, 2 animated antennas
- **Python API**: Simple motion control interface
- **Application Architecture**: Application system based on Hugging Face Spaces

### 3. reachy_mini_conversation_app
- **Architecture Pattern**: Layered architecture (User → AI Service → Robot Hardware)
- **Tech Stack**: OpenAI realtime API, Gradio, SmolVLM2 (local vision)
- **Tool System**: Extensible tool system (move_head, dance, play_emotion, etc.)

---

## 🎯 Project Goal

Port linux-voice-assistant to Reachy Mini to create a voice assistant controllable via Home Assistant, while integrating Reachy Mini's motion and expression capabilities.

---

## 📊 Project Plan (by Priority)

### Phase 1: Research and Architecture Design (High Priority)

1. **Research linux-voice-assistant Core Architecture and Code Structure**
   - Analyze code directory structure
   - Understand ESPHome protocol implementation
   - Identify reusable core modules
   - Evaluate dependencies and compatibility

2. **Analyze Reachy Mini SDK Hardware Interfaces and APIs**
   - Study audio interfaces (microphone/speaker)
   - Understand motion control APIs (head movements, expressions)
   - Test device compatibility

3. **Design Application Architecture and Interface Layer**
   - Design modular architecture (audio layer, voice layer, motion layer, communication layer)
   - Define interface specifications
   - Design configuration system
   - Plan error handling mechanisms

---

### Phase 2: Core Functionality Implementation (High Priority)

4. **Implement Audio Device Adapter Layer (Microphone/Speaker)**
   - Adapt to Reachy Mini's 4-microphone array
   - Implement 16KHz mono audio processing
   - Integrate echo cancellation (using PulseAudio or alternative)
   - Audio device discovery and management

5. **Port Wake Word Detection Module**
   - Integrate microWakeWord or openWakeWord
   - Support custom wake words
   - Optimize detection performance (low latency)

6. **Implement Audio Streaming to Home Assistant**
   - Stream audio data via ESPHome protocol
   - Ensure low-latency transmission (< 100ms)
   - Implement audio buffering
   - Handle connection stability and reconnection

---

### Phase 3: Feature Expansion (Medium Priority)

7. **Implement TTS Audio Reception from Home Assistant**
   - Receive TTS audio via ESPHome protocol
   - Real-time audio playback
   - Playback latency < 200ms
   - Audio queue management
   - Audio fade-in/fade-out

8. **Integrate Reachy Mini Motion Control**
   - Implement head motion control (nodding, shaking, turning)
   - Add expression system (based on reachy_mini_dances_library)
   - Create speech-reactive motions (micro-movements while speaking)

9. **Implement ESPHome Protocol Communication Layer**
   - Implement ESPHome server (port 6053)
   - Support Home Assistant integration
   - Implement command and state synchronization

---

### Phase 4: User Interface and Configuration (Low Priority)

10. **Develop Web UI (Gradio)**
    - Create settings interface
    - Display real-time status (wake up, recognition, motion)
    - Support configuration modification
    - Log viewing

11. **Implement Configuration Management System**
    - Support custom wake words
    - Audio device configuration
    - Motion parameter adjustment
    - ESPHome connection settings

12. **Write Test Cases and Documentation**
    - Unit tests
    - Integration tests
    - User documentation
    - API documentation

13. **Package and Publish to Hugging Face Spaces**
    - Create pyproject.toml
    - Configure dependencies
    - Write README
    - Publish application

---

## 🏗️ Suggested Project Structure

```
reachy_mini_ha_voice/
├── src/
│   └── reachy_mini_ha_voice/
│       ├── __init__.py
│       ├── main.py              # Application entry point
│       ├── audio/               # Audio processing module
│       │   ├── __init__.py
│       │   ├── adapter.py       # Audio device adapter
│       │   └── processor.py     # Audio processor
│       ├── voice/               # Voice processing module
│       │   ├── __init__.py
│       │   ├── detector.py      # Wake word detection
│       │   ├── stt.py           # STT (backup)
│       │   └── tts.py           # TTS (backup)
│       ├── motion/              # Motion control module
│       │   ├── __init__.py
│       │   ├── controller.py    # Motion controller
│       │   └── queue.py         # Motion queue
│       ├── esphome/             # ESPHome communication module
│       │   ├── __init__.py
│       │   ├── protocol.py      # Protocol definitions
│       │   └── server.py        # ESPHome server
│       └── config/              # Configuration management
│           ├── __init__.py
│           └── manager.py       # Config manager
├── profiles/                    # Personalization profiles
│   └── default/
│       ├── instructions.txt
│       └── tools.txt
├── wakewords/                   # Wake word models
├── pyproject.toml
├── README.md
├── README_CN.md
└── index.html                   # Hugging Face Space homepage
```

---

## 🔑 Key Technical Decisions

1. **Audio Processing**: Use Reachy Mini's 4-microphone array, may require microphone array processing algorithms
2. **STT Engine**: Handled by Home Assistant (via ESPHome protocol)
3. **TTS Engine**: Handled by Home Assistant (via ESPHome protocol)
4. **ESPHome Protocol**: Need to implement complete ESPHome API
5. **Motion Control**: Based on Reachy Mini SDK, add speech-reactive motions
6. **Audio Streaming**: Bidirectional audio streaming via ESPHome protocol

---

## ⚠️ Potential Challenges

1. **Audio Device Compatibility**: Reachy Mini's microphone array may require special handling
2. **Performance Optimization**: Running on Raspberry Pi 4 requires performance optimization
3. **ESPHome Protocol Implementation**: Need to implement complete ESPHome API
4. **Latency Control**: Need to minimize latency from voice recognition to motion response
5. **Audio Stream Synchronization**: Ensure audio stream synchronization with Home Assistant's STT/TTS processing
6. **Network Stability**: ESPHome connection requires stable network environment
7. **Bidirectional Audio**: Managing both audio streaming to Home Assistant and receiving TTS audio from Home Assistant

---

## 📝 Note on STT/TTS

**Important**: This project uses Home Assistant for STT and TTS processing. The application:
- Streams audio to Home Assistant for STT
- Receives TTS audio from Home Assistant for playback
- Only implements wake word detection locally on the robot
- Keeps Whisper and Piper engines as backup implementations

This design reduces computational load on the robot and leverages Home Assistant's powerful STT/TTS capabilities.