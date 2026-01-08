# Reachy Mini Home Assistant Voice Assistant - Project Plan

## Project Overview

Integrate Home Assistant voice assistant functionality into Reachy Mini Wi-Fi robot, communicating with Home Assistant via ESPHome protocol.

## Local Reference Directories (DO NOT modify any files in reference directories)
1. [linux-voice-assistant](reference/linux-voice-assistant) - Linux-based Home Assistant voice assistant app for reference
2. [Reachy Mini SDK](reference/reachy_mini) - Reachy Mini SDK local directory for reference
3. [reachy_mini_conversation_app](reference/reachy_mini_conversation_app) - Reachy Mini conversation app for reference
4. [reachy-mini-desktop-app](reference/reachy-mini-desktop-app) - Reachy Mini desktop app for reference
5. [sendspin](reference/sendspin-cli/) - Sendspin client for reference

## Core Design Principles

1. **Zero Configuration** - Users only need to install the app, no manual configuration required
2. **Native Hardware** - Use robot's built-in microphone and speaker
3. **Home Assistant Centralized Management** - All configuration done on Home Assistant side
4. **Motion Feedback** - Provide head movement and antenna animation feedback during voice interaction
5. **Project Constraints** - Strictly follow [Reachy Mini SDK](reachy_mini) architecture design and constraints
6. **Code Quality** - Follow Python development standards with consistent code style, clear structure, complete comments, comprehensive documentation
7. **Feature Priority** - Voice conversation with Home Assistant is highest priority; other features are auxiliary and must not affect voice conversation functionality or response speed
8. **No LED Functions** - LEDs are hidden inside the robot; all LED control is ignored
9. **Preserve Functionality** - Any code modifications should optimize while preserving completed features; do not remove features to solve problems

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Reachy Mini                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Microphone  │→ │ Wake Word   │→ │ ESPHome Protocol    │ │
│  │ (ReSpeaker) │  │ Detection   │  │ Server (Port 6053)  │ │
│  └─────────────┘  └─────────────┘  └──────────┬──────────┘ │
│                                                │            │
│  ┌─────────────┐  ┌─────────────┐             │            │
│  │ Speaker     │← │ Audio       │←────────────┘            │
│  │ (ReSpeaker) │  │ Player      │                          │
│  └─────────────┘  └─────────────┘                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Camera + Face Tracking (YOLO)                       │   │
│  │ - 15Hz face detection and tracking                  │   │
│  │ - look_at_image() calculates target pose            │   │
│  │ - Smooth return to neutral position after face lost │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Motion Controller (Head + Antennas) - 5Hz           │   │
│  │ - Face tracking offsets (secondary pose)            │   │
│  │ - Speech sway (voice-driven micro-movements)        │   │
│  │ - Breathing animation (idle breathing)              │   │
│  │ - on_wakeup → on_listening → on_speaking → on_idle  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ ESPHome Protocol
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Home Assistant                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ STT Engine  │  │ Intent      │  │ TTS Engine          │ │
│  │             │  │ Processing  │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Completed Features

### Core Features
- [x] ESPHome protocol server implementation
- [x] mDNS service discovery (auto-discovered by Home Assistant)
- [x] Local wake word detection (microWakeWord)
- [x] Tap-to-wake (IMU acceleration detection, wireless version only)
- [x] Audio stream transmission to Home Assistant
- [x] TTS audio playback
- [x] Stop word detection

### Reachy Mini Integration
- [x] Use Reachy Mini SDK microphone input
- [x] Use Reachy Mini SDK speaker output
- [x] Head motion control (nod, shake, gaze)
- [x] Antenna animation control
- [x] Voice state feedback actions
- [x] YOLO face tracking (replaces DOA sound source localization)
- [x] 5Hz unified motion control loop

### Application Architecture
- [x] Compliant with Reachy Mini App architecture
- [x] Auto-download wake word models
- [x] Auto-download sound effect files
- [x] No .env configuration file required

## File List

```
reachy_mini_ha_voice/
├── reachy_mini_ha_voice/
│   ├── __init__.py             # Package initialization
│   ├── __main__.py             # Command line entry
│   ├── main.py                 # ReachyMiniApp entry
│   ├── voice_assistant.py      # Voice assistant service
│   ├── satellite.py            # ESPHome protocol handling
│   ├── audio_player.py         # Audio player
│   ├── camera_server.py        # MJPEG camera stream server + face tracking
│   ├── head_tracker.py         # YOLO face detector
│   ├── motion.py               # Motion control (high-level API)
│   ├── movement_manager.py     # Unified movement manager (20Hz control loop)
│   ├── models.py               # Data models
│   ├── entity.py               # ESPHome base entity
│   ├── entity_extensions.py    # Extended entity types
│   ├── reachy_controller.py    # Reachy Mini controller wrapper
│   ├── api_server.py           # API server
│   ├── zeroconf.py             # mDNS discovery
│   └── util.py                 # Utility functions
├── wakewords/                  # Wake word models (auto-download)
├── sounds/                     # Sound effect files (auto-download)
├── pyproject.toml              # Project configuration
├── README.md                   # Documentation
└── PROJECT_PLAN.md             # Project plan
```

## Usage Flow

1. **Install App** - Install `reachy-mini-ha-voice` from Reachy Mini App Store
2. **Start App** - App auto-starts ESPHome server (port 6053), auto-downloads required models and sounds
3. **Connect Home Assistant** - Home Assistant auto-discovers device (mDNS) or manually add via Settings → Devices & Services → Add Integration → ESPHome
4. **Use Voice Assistant** - Say "Okay Nabu" to wake, speak command, Reachy Mini provides motion feedback

---

## ESPHome Entity Implementation

### Completed Entities Summary

**Total: 43+ entities implemented**
- Phase 1-4: Basic controls, motor control, pose control, gaze control
- Phase 5-7: Audio sensors, diagnostics, IMU sensors
- Phase 8-12: Emotion control, microphone volume, camera, audio processing
- Phase 13: Sendspin audio output support

### Control Entities (Read/Write)

| Entity Type | Name | Description |
|-------------|------|-------------|
| `Number` | `speaker_volume` | Speaker volume (0-100) |
| `Select` | `motor_mode` | Motor mode (enabled/disabled/gravity_compensation) |
| `Switch` | `motors_enabled` | Motor torque switch |
| `Button` | `wake_up` / `go_to_sleep` | Wake/sleep robot actions |
| `Number` | `head_x/y/z` | Head position control (±50mm) |
| `Number` | `head_roll/pitch/yaw` | Head angle control |
| `Number` | `body_yaw` | Body yaw angle (-160° ~ +160°) |
| `Number` | `antenna_left/right` | Antenna angle control (±90°) |
| `Number` | `look_at_x/y/z` | Gaze point coordinates |
| `Select` | `emotion` | Emotion selector (Happy/Sad/Angry/Fear/Surprise/Disgust) |
| `Number` | `microphone_volume` | Microphone volume (0-100%) |
| `Switch` | `agc_enabled` | Auto gain control switch |
| `Number` | `agc_max_gain` | AGC max gain (0-30 dB) |
| `Number` | `noise_suppression` | Noise suppression level (0-100%) |
| `Number` | `tap_sensitivity` | Tap detection sensitivity (0.5-4.0g) |
| `Switch` | `sendspin_enabled` | Sendspin switch |

### Sensor Entities (Read-only)

| Entity Type | Name | Description |
|-------------|------|-------------|
| `Text Sensor` | `daemon_state` | Daemon status |
| `Binary Sensor` | `backend_ready` | Backend ready status |
| `Text Sensor` | `error_message` | Current error message |
| `Sensor` | `doa_angle` | Sound source direction angle |
| `Binary Sensor` | `speech_detected` | Speech detection status |
| `Sensor` | `control_loop_frequency` | Control loop frequency (Hz) |
| `Text Sensor` | `sdk_version` | SDK version |
| `Text Sensor` | `robot_name` | Robot name |
| `Binary Sensor` | `wireless_version` | Wireless version flag |
| `Binary Sensor` | `simulation_mode` | Simulation mode flag |
| `Text Sensor` | `wlan_ip` | Wireless IP address |
| `Sensor` | `imu_accel_x/y/z` | Accelerometer (m/s²) |
| `Sensor` | `imu_gyro_x/y/z` | Gyroscope (rad/s) |
| `Sensor` | `imu_temperature` | IMU temperature (°C) |
| `Binary Sensor` | `echo_cancellation_converged` | Echo cancellation convergence status |
| `Camera` | `camera` | ESPHome Camera entity |
| `Text Sensor` | `sendspin_url` | Sendspin server URL |
| `Binary Sensor` | `sendspin_connected` | Sendspin connection status |

---

## Voice Assistant Enhancement Features

### Phase 14 - Emotion Action Feedback System 🟡 Partial

**Status**: Basic infrastructure ready, supports manual trigger, uses voice-driven natural micro-movements during conversation

**Implemented**:
- ✅ Emotion Selector entity (`emotion`)
- ✅ Basic emotion action playback API (`_play_emotion`)
- ✅ Emotion mapping: Happy/Sad/Angry/Fear/Surprise/Disgust
- ✅ Integration with HuggingFace action library
- ✅ SpeechSway system for natural head micro-movements during conversation

**Design Decisions**:
- 🎯 No auto-play of full emotion actions during conversation to avoid blocking
- 🎯 Use voice-driven head sway (SpeechSway) for natural motion feedback
- 🎯 Emotion actions retained as manual trigger feature via ESPHome entity

### Phase 15 - Face Tracking (Replaces DOA) ✅ Complete

**Goal**: Implement natural face tracking so robot looks at speaker during conversation.

**Design Decision**: 
- ❌ Original plan: DOA (Direction of Arrival) sound source tracking
- ✅ Changed to: YOLO face detection - more stable and accurate
- Reason: DOA inaccurate at wakeup, frequent queries cause daemon crash

**Implemented Features**:
- ✅ YOLO face detection using `AdamCodd/YOLOv11n-face-detection` model
- ✅ Adaptive frame rate: 15fps during conversation, 3fps when idle without face
- ✅ look_at_image() calculates target pose from face position
- ✅ Smooth return to neutral position after face lost (1 second)
- ✅ face_tracking_offsets as secondary pose overlay
- ✅ Model download retry (3 attempts, 5s interval)
- ✅ Conversation mode integration with voice assistant state

**Resource Optimization (v0.5.1)**:
- During conversation (listening/thinking/speaking): High-frequency tracking 15fps
- Idle with face detected: High-frequency tracking 15fps
- Idle without face for 10s: Low-power mode 3fps
- Immediately restore high-frequency tracking when face detected

### Phase 16 - Cartoon Style Motion Mode 🟡 Partial

**Goal**: Use SDK interpolation techniques for more expressive robot movements.

**Implemented**:
- ✅ 20Hz unified control loop (reduced from 100Hz to prevent daemon crash)
- ✅ Pose change detection - only send commands on significant changes (threshold 0.001)
- ✅ State query caching - 100ms TTL, reduces daemon load
- ✅ Smooth interpolation (ease in-out curve)
- ✅ Breathing animation - idle Z-axis micro-movement + antenna sway
- ✅ Command queue mode - thread-safe external API
- ✅ Error throttling - prevents log explosion
- ✅ Connection health monitoring - auto-detect and recover from connection loss

**Not Implemented**:
- ❌ Dynamic interpolation technique switching (CARTOON/EASE_IN_OUT etc.)
- ❌ Exaggerated cartoon bounce effects

### Phase 17 - Antenna Sync Animation During Speech 🟡 Partial

**Goal**: Antennas sway with audio rhythm during TTS playback, simulating "speaking" effect.

**Implemented**:
- ✅ Voice-driven head sway (`SpeechSwayGenerator`)
- ✅ VAD detection based on audio loudness
- ✅ Multi-frequency sine wave overlay (Lissajous motion)
- ✅ Smooth envelope transitions

**Not Implemented**:
- ❌ Antenna sway with audio rhythm (currently only head sway)
- ❌ Audio spectrum analysis driven animation

### Phase 18 - Visual Gaze Interaction ❌ Not Implemented

**Goal**: Use camera to detect faces for eye contact.

### Phase 19 - Gravity Compensation Interactive Mode 🟡 Partial

**Implemented**:
- ✅ Gravity compensation mode switch (`motor_mode` Select entity)

**Not Implemented**:
- ❌ Teaching mode - record motion trajectory
- ❌ Save/playback custom actions

### Phase 20 - Environment Awareness Response 🟡 Partial

**Implemented**:
- ✅ Tap-to-wake enters continuous conversation mode
- ✅ Second tap exits continuous conversation mode

**Tap-to-wake vs Voice Wake**:
| Wake Method | Conversation Mode | Description |
|-------------|-------------------|-------------|
| Voice wake (Okay Nabu) | Single conversation | Need to say wake word for each conversation |
| Tap-to-wake | Continuous conversation | Auto-continue listening after TTS ends, tap again to exit |

**Not Implemented**:
- ❌ Shake detection - play dizzy action
- ❌ Tilt/fall detection - play help action
- ❌ Long idle - enter sleep animation

### Phase 21 - Home Assistant Scene Integration ❌ Not Implemented

---

## Completion Statistics

| Phase | Status | Completion | Notes |
|-------|--------|------------|-------|
| Phase 1-12 | ✅ Complete | 100% | 40 ESPHome entities implemented (Phase 11 LED disabled) |
| Phase 13 | ✅ Complete | 100% | Sendspin audio output support |
| Phase 14 | 🟡 Partial | 30% | API infrastructure ready, missing auto-trigger |
| Phase 15 | ✅ Complete | 100% | YOLO face tracking fully implemented |
| Phase 16 | 🟡 Partial | 70% | Control loop + pose detection + breathing animation |
| Phase 17 | 🟡 Partial | 50% | Voice-driven head sway implemented |
| Phase 18 | ❌ Not done | 10% | Camera implemented, missing face detection |
| Phase 19 | 🟡 Partial | 40% | Mode switch implemented, missing teaching flow |
| Phase 20 | 🟡 Partial | 30% | Tap-to-wake implemented |
| Phase 21 | ❌ Not done | 0% | Not implemented |

**Overall Completion**: **Phase 1-13: 100%** | **Phase 14-21: ~45%**

---

## Bug Fixes History

### v0.5.1 Bug Fixes (2026-01-08)

#### Issue 1: Music Not Resuming After Voice Conversation
**Problem**: Music doesn't resume after voice conversation ends.
**Root Cause**: Sendspin was incorrectly connected to `tts_player` instead of `music_player`.
**Fix**: 
- `voice_assistant.py`: Sendspin discovery now connects to `music_player`
- `satellite.py`: `duck()`/`unduck()` now call `music_player.pause_sendspin()`/`resume_sendspin()`

#### Issue 2: tap_sensitivity Not Persisted
**Problem**: tap_sensitivity value set in ESPHome lost after restart.
**Fix**:
- `models.py`: Added `tap_sensitivity` field to `Preferences` dataclass
- `entity_registry.py`: Entity setter now saves to `preferences.json`
- Load saved value on startup

#### Issue 3: Audio Conflict During Voice Assistant Wakeup
**Problem**: Audio streaming (Sendspin or ESPHome audio) conflicts when voice assistant wakes up.
**Fix**:
- `audio_player.py`: Added `pause_sendspin()` and `resume_sendspin()` methods
- `satellite.py`: `duck()` now pauses Sendspin, `unduck()` resumes it
- Improved `pause()` method to actually stop audio output

#### Issue 4: AttributeError for _camera_server
**Problem**: `_set_conversation_mode()` referenced non-existent `_camera_server` attribute.
**Fix**: Changed `self._camera_server` to `self.camera_server` (removed underscore prefix)

#### Issue 5: tap_sensitivity Default Value Wrong
**Problem**: tap_sensitivity default was still 2.0g instead of expected 0.5g.
**Fix**: Use `TAP_THRESHOLD_G_DEFAULT` constant as default value

#### Issue 6: Sendspin Sample Rate Optimization
**Problem**: ReSpeaker hardware I/O is 16kHz (hardware limitation), but Sendspin might try higher sample rates.
**Fix**: Prioritize 16kHz in Sendspin supported formats list to avoid unnecessary resampling

### Daemon Crash Fix (2026-01-07)

**Problem**: `reachy_mini daemon` crashes during long-term operation.

**Root Cause Analysis**:
1. Each `set_target()` sends 3 Zenoh messages
2. Daemon control loop is 50Hz
3. Previous 20Hz control loop still too high (20Hz × 3 = 60 msg/s > 50Hz capacity)
4. Pose change threshold too small (0.002) - almost every loop triggers `set_target()`

**Fix**:
- Control loop frequency: 20Hz → 10Hz
- Pose change threshold: 0.002 → 0.005
- Camera/face tracking frequency: 15fps → 10fps
- IMU polling frequency: 50Hz → 20Hz
- State cache TTL: 1s → 2s

**Results**:
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Control loop frequency | 20 Hz | 10 Hz | ↓ 50% |
| Max Zenoh messages | 60 msg/s | 30 msg/s | ↓ 50% |
| Expected stability | Hours before crash | Stable operation | Significant |

### Tap-to-Wake and Microphone Sensitivity Fix (2026-01-07)

**Problems**:
1. Tap-to-wake blocking - conversation not working properly after tap wake
2. Low microphone sensitivity - need to be very close for voice recognition

**Fixes**:
1. Removed audio playback in `_tap_continue_feedback()` to avoid blocking
2. Comprehensive microphone optimization:
   - AGC enabled with max gain 30dB
   - AGC desired level -18dB
   - Base microphone gain 2.0x
   - Noise suppression reduced to 0.15
   - Echo cancellation and high-pass filter enabled

**Results**:
| Parameter | Before | After |
|-----------|--------|-------|
| Microphone sensitivity | ~30cm | ~2-3m |
| AGC max gain | ~15dB | 30dB |
| Noise suppression | ~0.5 | 0.15 |

---

## SDK Data Structure Reference

```python
# Motor control mode
class MotorControlMode(str, Enum):
    Enabled = "enabled"              # Torque on, position control
    Disabled = "disabled"            # Torque off
    GravityCompensation = "gravity_compensation"  # Gravity compensation mode

# Daemon state
class DaemonState(Enum):
    NOT_INITIALIZED = "not_initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

# Safety limits
HEAD_PITCH_ROLL_LIMIT = [-40°, +40°]
HEAD_YAW_LIMIT = [-180°, +180°]
BODY_YAW_LIMIT = [-160°, +160°]
YAW_DELTA_MAX = 65°  # Max difference between head and body yaw
```

## Reference Projects

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)
- [pollen-robotics/reachy_mini](https://github.com/pollen-robotics/reachy_mini)
