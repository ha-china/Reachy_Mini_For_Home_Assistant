# Reachy Mini Home Assistant Voice Assistant - Requirements Document

## 1. Project Overview

### 1.1 Project Goal
Develop a Home Assistant voice assistant application for Reachy Mini robot that can:
- Interact with users via voice
- Integrate with Home Assistant smart home system
- Display rich expressions and movements
- Support offline wake word detection
- Provide low-latency voice responses

### 1.2 Target Users
- Home Assistant users
- Reachy Mini robot owners
- Smart home enthusiasts
- Robot developers

### 1.3 Application Scenarios
- Home voice control center
- Smart home interaction interface
- Companion robot assistant
- Education and entertainment platform

## 2. Functional Requirements

### 2.1 Core Features

#### FR-1: Audio Input
**Description**: The system must be able to capture audio data from Reachy Mini's 4-microphone array.

**Detailed Requirements**:
- Sample rate: 16kHz
- Channels: Mono
- Format: 16-bit PCM (little-endian)
- Block size: 1024 samples
- Support echo cancellation
- Support automatic device detection

**Acceptance Criteria**:
- Able to continuously record audio stream
- Clear audio quality without significant noise
- Latency < 100ms

#### FR-2: Audio Output
**Description**: The system must be able to play audio through Reachy Mini's 5W speaker.

**Detailed Requirements**:
- Sample rate: 16kHz
- Channels: Mono
- Support volume control
- Support playback queue management
- Support audio fade-in/fade-out

**Acceptance Criteria**:
- Clear audio playback without distortion
- Smooth audio switching
- Support playing multiple audio streams simultaneously (mixing)

#### FR-3: Wake Word Detection
**Description**: The system must be able to detect predefined wake words.

**Detailed Requirements**:
- Support microWakeWord models
- Support openWakeWord models
- Support custom wake words
- Detection latency < 500ms
- Accuracy > 95%
- Support multiple wake words active simultaneously
- Support cooldown period (prevent repeated triggering)

**Acceptance Criteria**:
- Accuracy > 95% in quiet environments
- Accuracy > 90% in moderate noise environments
- False positive rate < 1%

#### FR-4: Audio Streaming to Home Assistant
**Description**: The system must be able to stream audio data to Home Assistant for STT processing via ESPHome protocol.

**Detailed Requirements**:
- Use ESPHome protocol
- Real-time audio data transmission
- Transmission latency < 100ms
- Support audio buffering
- Support disconnection and reconnection
- Support multiple client connections

**Acceptance Criteria**:
- Stable audio transmission
- Transmission latency < 100ms
- Support long-time streaming
- Automatic reconnection after disconnection

#### FR-5: Receive TTS Audio from Home Assistant
**Description**: The system must be able to receive TTS audio from Home Assistant and play it.

**Detailed Requirements**:
- Receive audio via ESPHome protocol
- Real-time audio playback
- Playback latency < 200ms
- Support audio queue management
- Support audio fade-in/fade-out

**Acceptance Criteria**:
- Clear audio playback without distortion
- Playback latency < 200ms
- Support smooth audio switching
- Audio queue working properly

#### FR-6: Head Motion Control
**Description**: The system must be able to control Reachy Mini's head movements.

**Detailed Requirements**:
- Support 6-DOF motion
- Support nodding, shaking, turning
- Support smooth motion interpolation
- Support motion queue (priority-based)
- Support motion cancellation

**Acceptance Criteria**:
- Smooth motion without jerking
- Accurate position control
- Queue priority working properly
- Motion cancellation working properly

#### FR-7: Antenna Animation
**Description**: The system must be able to animate Reachy Mini's two antennas.

**Detailed Requirements**:
- Independent control of two antennas
- Support continuous animation
- Support angle control
- Support speed control
- Support predefined animations

**Acceptance Criteria**:
- Smooth antenna movement
- Accurate angle control
- Predefined animations working properly

#### FR-8: Speech-Reactive Motions
**Description**: The system must be able to generate motions synchronized with speech.

**Detailed Requirements**:
- Automatic motion generation during TTS playback
- Support different motion types (nodding, looking around, etc.)
- Synchronize with TTS audio
- Configurable motion intensity

**Acceptance Criteria**:
- Motion synchronized with speech
- Natural and smooth motions
- Configurable intensity

#### FR-9: ESPHome Communication
**Description**: The system must communicate with Home Assistant via ESPHome protocol.

**Detailed Requirements**:
- Implement ESPHome protocol server
- Listen port: 6053
- Support voice events (wake word, TTS start/end, STT results)
- Support bidirectional audio streaming (to Home Assistant and from Home Assistant)
- Support mDNS service discovery
- Support device information query

**Acceptance Criteria**:
- Can be automatically discovered by Home Assistant
- Can receive and send voice events
- Can transmit bidirectional audio streams
- Stable connection, automatic reconnection on disconnection

#### FR-10: Configuration Management
**Description**: The system must support flexible configuration.

**Detailed Requirements**:
- Support configuration file (JSON)
- Support environment variables
- Support command-line arguments
- Support default configuration
- Support hot reload of non-critical configurations

**Acceptance Criteria**:
- Configuration file loading correctly
- Environment variables working properly
- Command-line arguments overriding other configurations
- Default configuration working properly

### 2.2 Extended Features

#### EF-1: Web UI
**Description**: Provide a web-based user interface for configuration and monitoring.

**Detailed Requirements**:
- Use Gradio framework
- Display real-time status
- Support configuration modification
- Support log viewing
- Support device testing

**Acceptance Criteria**:
- UI accessible via browser
- Real-time status updates
- Configuration changes taking effect

#### EF-2: Face Tracking
**Description**: Support face detection and tracking.

**Detailed Requirements**:
- Use camera for face detection
- Head follows face movement
- Support multiple faces
- Configurable tracking sensitivity

**Acceptance Criteria**:
- Accurate face detection
- Smooth tracking
- Configurable sensitivity

#### EF-3: Visual Recognition
**Description**: Support object and scene recognition.

**Detailed Requirements**:
- Use SmolVLM2 model
- Real-time image analysis
- Support custom prompts
- Configurable recognition interval

**Acceptance Criteria**:
- Accurate recognition
- Reasonable processing speed
- Custom prompts working properly

#### EF-4: Advanced Emotions
**Description**: Support rich emotional expressions.

**Detailed Requirements**:
- Based on reachy_mini_dances_library
- Support multiple emotion types
- Support emotion queue
- Support emotion intensity control

**Acceptance Criteria**:
- Smooth emotion transitions
- Multiple emotion types working
- Queue priority working properly

## 3. Technical Requirements

### 3.1 Hardware Requirements

**Minimum Requirements**:
- Raspberry Pi 4 (4GB RAM)
- Reachy Mini robot hardware
- 4-microphone array
- 5W speaker
- Head motors (6 DOF)
- 2 antennas
- Camera (optional)
- Network connection (WiFi or Ethernet)

**Recommended Requirements**:
- Raspberry Pi 4 (8GB RAM)
- Stable high-speed network

### 3.2 Software Requirements

**Operating System**:
- Raspberry Pi OS (64-bit recommended)
- Ubuntu 22.04 LTS or later

**Python**:
- Python 3.8 or higher
- Python 3.11/3.13 recommended

**Dependencies**:
- aioesphomeapi >= 42.0
- soundcard < 1
- numpy >= 2, < 3
- pymicro-wakeword >= 2, < 3
- pyopen-wakeword >= 1, < 2
- python-mpv >= 1, < 2
- zeroconf < 1
- reachy-mini-sdk (latest)
- asyncio
- pydantic

**Optional Dependencies**:
- Gradio (for Web UI)
- SmolVLM2 (for visual recognition)
- reachy_mini_dances_library (for advanced emotions)

### 3.3 Network Requirements

**Bandwidth**:
- Minimum: 1 Mbps (for audio streaming)
- Recommended: 5 Mbps (for audio + video)

**Latency**:
- Local network: < 10ms
- Remote access: < 100ms

**Protocol**:
- ESPHome protocol (TCP)
- mDNS (for service discovery)

## 4. Non-Functional Requirements

### 4.1 Performance Requirements

**Response Time**:
- Wake word detection: < 500ms
- Audio streaming latency: < 100ms
- TTS playback latency: < 200ms
- Motion response: < 100ms
- Overall voice interaction: < 2s

**Throughput**:
- Audio streaming: 16kHz continuous
- Support multiple concurrent connections

**Resource Usage**:
- CPU usage: < 50% (idle), < 80% (peak)
- RAM usage: < 2GB
- Disk usage: < 500MB (excluding models)

### 4.2 Reliability Requirements

**Availability**:
- Uptime: > 99%
- Mean Time Between Failures (MTBF): > 720 hours
- Mean Time To Recovery (MTTR): < 5 minutes

**Error Handling**:
- Graceful handling of audio device errors
- Automatic reconnection on network disconnection
- Error logging and reporting
- User-friendly error messages

### 4.3 Maintainability Requirements

**Code Quality**:
- Follow PEP 8 style guide
- Code coverage > 80%
- Comprehensive documentation
- Clear code structure

**Testing**:
- Unit tests for all modules
- Integration tests for key features
- Manual testing checklist

**Documentation**:
- API documentation
- User manual
- Developer guide
- Troubleshooting guide

### 4.4 Security Requirements

**Data Privacy**:
- Audio data encrypted during transmission
- No audio data stored locally (optional)
- Clear audio recording indicators

**Access Control**:
- ESPHome authentication (optional)
- Network access control
- Secure configuration storage

**Vulnerability Management**:
- Regular dependency updates
- Security vulnerability scanning
- Prompt security patching

### 4.5 Compatibility Requirements

**Platform Compatibility**:
- Raspberry Pi OS
- Ubuntu 22.04 LTS or later
- Debian 12 or later

**Home Assistant Compatibility**:
- Home Assistant 2024.7.0 or later
- ESPHome integration

**Hardware Compatibility**:
- Reachy Mini (all versions)
- Standard USB microphones/speakers (fallback)

## 5. Constraints

### 5.1 Technical Constraints

**Processing Power**:
- Limited to Raspberry Pi 4 capabilities
- Need to optimize for low-power devices

**Network**:
- Requires stable network connection
- May experience latency on remote connections

**Audio**:
- Requires specific audio format (16kHz mono)
- May need echo cancellation

### 5.2 Time Constraints

**Development Timeline**:
- Phase 1 (Research & Design): 2 weeks
- Phase 2 (Core Features): 4 weeks
- Phase 3 (Extended Features): 3 weeks
- Phase 4 (Testing & Documentation): 2 weeks

### 5.3 Resource Constraints

**Development Resources**:
- Limited development team size
- Limited testing hardware availability

**Budget Constraints**:
- Use open-source libraries where possible
- Minimize cloud service dependencies

### 5.4 Compliance Constraints

**Open Source**:
- Apache 2.0 license
- Proper attribution to original projects

**Privacy**:
- Comply with data privacy regulations
- User consent for audio data collection

## 6. Acceptance Criteria

### 6.1 Functional Acceptance

**Core Features**:
- [ ] All FR-1 to FR-10 requirements met
- [ ] All acceptance criteria passed
- [ ] Integration with Home Assistant working
- [ ] Wake word detection accuracy > 95%
- [ ] Audio streaming stable
- [ ] Motion control smooth

**Extended Features**:
- [ ] EF-1 to EF-4 requirements met (if implemented)
- [ ] Web UI functional
- [ ] Face tracking accurate
- [ ] Visual recognition working

### 6.2 Performance Acceptance

**Response Time**:
- [ ] Wake word detection < 500ms
- [ ] Audio streaming < 100ms
- [ ] TTS playback < 200ms
- [ ] Motion response < 100ms

**Resource Usage**:
- [ ] CPU usage < 80% (peak)
- [ ] RAM usage < 2GB
- [ ] Disk usage < 500MB

### 6.3 Quality Acceptance

**Code Quality**:
- [ ] Code coverage > 80%
- [ ] No critical bugs
- [ ] All tests passing
- [ ] Code review approved

**Documentation**:
- [ ] API documentation complete
- [ ] User manual complete
- [ ] Developer guide complete
- [ ] README complete

### 6.4 Documentation Acceptance

**User Documentation**:
- [ ] Installation guide
- [ ] Configuration guide
- [ ] Usage guide
- [ ] Troubleshooting guide

**Developer Documentation**:
- [ ] Architecture document
- [ ] API reference
- [ ] Development guide
- [ ] Testing guide

## 7. Risk Assessment

### 7.1 Technical Risks

**High Risk**:
- ESPHome protocol implementation complexity
- Audio synchronization issues
- Network stability affecting performance

**Medium Risk**:
- Wake word detection accuracy
- Motion control smoothness
- Resource constraints on Raspberry Pi

**Low Risk**:
- Configuration management
- Web UI development
- Documentation

### 7.2 Resource Risks

**High Risk**:
- Limited testing hardware availability
- Development team size constraints

**Medium Risk**:
- Timeline pressure
- Budget constraints

**Low Risk**:
- Open source library availability
- Community support

### 7.3 Dependency Risks

**High Risk**:
- Reachy Mini SDK changes
- Home Assistant API changes

**Medium Risk**:
- Third-party library compatibility
- Dependency version conflicts

**Low Risk**:
- Python version compatibility
- Operating system compatibility

## 8. Success Metrics

### 8.1 Technical Metrics

**Performance**:
- Wake word detection accuracy > 95%
- Audio streaming latency < 100ms
- TTS playback latency < 200ms
- Motion response time < 100ms

**Reliability**:
- Uptime > 99%
- MTBF > 720 hours
- MTTR < 5 minutes

**Quality**:
- Code coverage > 80%
- Bug count < 5 (critical)
- User satisfaction > 4/5

### 8.2 User Metrics

**Adoption**:
- Number of installations
- Number of active users
- User retention rate

**Usage**:
- Average daily usage time
- Number of voice interactions
- Feature usage statistics

**Satisfaction**:
- User satisfaction score
- Feature request count
- Bug report count

### 8.3 Business Metrics

**Community**:
- GitHub stars
- Forks
- Contributors

**Support**:
- Issue resolution time
- Documentation completeness
- Community engagement

## 9. Future Enhancements

### 9.1 Short-term (3-6 months)

- Improve wake word accuracy
- Add more wake word models
- Optimize performance
- Enhance error handling

### 9.2 Medium-term (6-12 months)

- Add face tracking
- Implement visual recognition
- Add advanced emotions
- Improve motion library

### 9.3 Long-term (12+ months)

- Multi-language support
- Cloud integration options
- Advanced AI features
- Mobile app support

---

**Note**: This requirements document is the English version of REQUIREMENTS.md. For the Chinese version, see REQUIREMENTS.md.