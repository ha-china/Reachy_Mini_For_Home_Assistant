# Reachy Mini for Home Assistant - Project Plan

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
6. **Code Quality** - Follow Python development standards with consistent code style, clear structure, complete comments, comprehensive documentation, high test coverage, high code quality, readability, maintainability, extensibility, and reusability
7. **Feature Priority** - Voice conversation with Home Assistant is highest priority; other features are auxiliary and must not affect voice conversation functionality or response speed
8. **No LED Functions** - LEDs are hidden inside the robot; all LED control is ignored
9. **Preserve Functionality** - Any code modifications should optimize while preserving completed features; do not remove features to solve problems. When issues occur, prioritize solving problems after referencing examples, not adding various log outputs

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Reachy Mini (ARM64)                            │
│                                                                             │
│  ┌─────────────────────────────── AUDIO INPUT ───────────────────────────┐  │
│  │  ReSpeaker XVF3800 (16kHz)                                            │  │
│  │  ┌──────────────┐   ┌──────────────────────────────────────────────┐  │  │
│  │  │ 4-Mic Array  │ → │ XVF3800 DSP                                  │  │  │
│  │  └──────────────┘   │ • Echo Cancellation (AEC)                    │  │  │
│  │                     │ • Noise Suppression (NS)                     │  │  │
│  │                     │ • Auto Gain Control (AGC, max 30dB)          │  │  │
│  │                     │ • Direction of Arrival (DOA)                 │  │  │
│  │                     │ • Voice Activity Detection (VAD)             │  │  │
│  │                     └──────────────────────────────────────────────┘  │  │
│  │                                      │                                │  │
│  │                                      ▼                                │  │
│  │                     ┌──────────────────────────────────────────────┐  │  │
│  │                     │ Wake Word Detection (microWakeWord)          │  │  │
│  │                     │ • "Okay Nabu" / "Hey Jarvis"                 │  │  │
│  │                     │ • Stop word detection                        │  │  │
│  │                     └──────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────── AUDIO OUTPUT ──────────────────────────┐  │
│  │  ┌──────────────────────────┐    ┌──────────────────────────────────┐ │  │
│  │  │ TTS Player               │    │ Music Player (Sendspin)          │ │  │
│  │  │ • Voice assistant speech │    │ • Multi-room audio streaming     │ │  │
│  │  │ • Sound effects          │    │ • Auto-discovery via mDNS        │ │  │
│  │  │ • Priority over music    │    │ • Auto-pause during conversation │ │  │
│  │  └──────────────────────────┘    └──────────────────────────────────┘ │  │
│  │                 │                              │                      │  │
│  │                 └──────────────┬───────────────┘                      │  │
│  │                                ▼                                      │  │
│  │                 ┌──────────────────────────────────────────────────┐  │  │
│  │                 │ ReSpeaker Speaker (16kHz)                        │  │  │
│  │                 └──────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────── VISION & TRACKING ─────────────────────────┐  │
│  │  ┌──────────────────────────┐    ┌──────────────────────────────────┐ │  │
│  │  │ Camera (VPU accelerated) │ →  │ YOLO Face Detection              │ │  │
│  │  │ • MJPEG stream server    │    │ • AdamCodd/YOLOv11n-face         │ │  │
│  │  │ • ESPHome Camera entity  │    │ • Adaptive frame rate:           │ │  │
│  │  └──────────────────────────┘    │   - 15fps: conversation/face     │ │  │
│  │                                  │   - 2fps: idle (power saving)    │ │  │
│  │                                  │ • look_at_image() pose calc      │ │  │
│  │                                  │ • Smooth return after face lost  │ │  │
│  │                                  └──────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────── MOTION CONTROL ────────────────────────────┐  │
│  │  MovementManager (100Hz Control Loop)                                 │  │
│  │  ┌────────────────────────────────────────────────────────────────┐   │  │
│  │  │ Motion Layers (Priority: Move > Action > SpeechSway > Breath)  │   │  │
│  │  │ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │   │  │
│  │  │ │ Move Queue │ │ Actions    │ │ SpeechSway │ │ Breathing    │  │   │  │
│  │  │ │ (Emotions) │ │ (Nod/Shake)│ │ (Voice VAD)│ │ (Idle anim)  │  │   │  │
│  │  │ └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  │                                                                       │  │
│  │  ┌────────────────────────────────────────────────────────────────┐   │  │
│  │  │ Face Tracking Offsets (Secondary Pose Overlay)                 │   │  │
│  │  │ • Pitch offset: +9° (down compensation)                        │   │  │
│  │  │ • Yaw offset: -7° (right compensation)                         │   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  │                                                                       │  │
│  │   State Machine: on_wakeup → on_listening → on_speaking → on_idle     │  │
│  │                                                                       │  │
│  │  ┌────────────────────────────────────────────────────────────────┐   │  │
│  │  │ Body Following (v0.8.3)                                        │   │  │
│  │  │ • Body yaw syncs with head yaw for natural tracking            │   │  │
│  │  │ • Extracted from final head pose matrix                        │   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────── GESTURE DETECTION ────────────────────────┐  │
│  │  HaGRID ONNX Models                                                  │  │
│  │  • 18 gesture classes (call, like, dislike, fist, ok, palm, etc.)    │  │
│  │  • Only runs when face detected (power saving)                       │  │
│  │  • Real-time state push to Home Assistant                            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────── ESPHOME SERVER ────────────────────────────┐  │
│  │  Port 6053 (mDNS auto-discovery)                                      │  │
│  │  • 43+ entities (sensors, controls, media player, camera)             │  │
│  │  • Voice Assistant pipeline integration                               │  │
│  │  • Real-time state synchronization                                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ ESPHome Protocol (protobuf)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Home Assistant                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────────┐ │
│  │ STT Engine       │  │ Intent Processing│  │ TTS Engine                 │ │
│  │ (User configured)│  │ (Conversation)   │  │ (User configured)          │ │
│  └──────────────────┘  └──────────────────┘  └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Completed Features

### Core Features
- [x] ESPHome protocol server implementation
- [x] mDNS service discovery (auto-discovered by Home Assistant)
- [x] Local wake word detection (microWakeWord)
- [x] Continuous conversation mode (controlled via Home Assistant switch)
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
- [x] 100Hz unified motion control loop

### Application Architecture
- [x] Compliant with Reachy Mini App architecture



## File List

```
reachy_mini_ha_voice/
├── reachy_mini_ha_voice/
│   ├── __init__.py             # Package initialization
│   ├── __main__.py             # Command line entry
│   ├── main.py                 # ReachyMiniApp entry
│   ├── voice_assistant.py      # Voice assistant service
│   ├── satellite.py            # ESPHome protocol handling
│   ├── audio_player.py         # Audio player (TTS + Sendspin)
│   ├── camera_server.py        # MJPEG camera stream server + face tracking
│   ├── head_tracker.py         # YOLO face detector
│   ├── motion.py               # Motion control (high-level API)
│   ├── movement_manager.py     # Unified movement manager (100Hz control loop)
│   ├── animation_player.py     # JSON-driven animation system
│   ├── speech_sway.py          # Voice-driven head micro-movements
│   ├── models.py               # Data models
│   ├── entity.py               # ESPHome base entity
│   ├── entity_extensions.py    # Extended entity types
│   ├── entity_registry.py      # Entity registry
│   ├── reachy_controller.py    # Reachy Mini controller wrapper
│   ├── gesture_detector.py     # HaGRID gesture detection
│   ├── api_server.py           # HTTP API server
│   ├── zeroconf.py             # mDNS discovery (ESPHome + Sendspin)
│   └── util.py                 # Utility functions
│   └── animations/             # Animation definitions
│       ├── conversation_animations.json  # Conversation state animations
│       └── emotion_keywords.json         # Emotion keyword mapping (280+ keywords)
│   └── wakewords/              # Wake word models
│       ├── okay_nabu.json/.tflite
│       ├── hey_jarvis.json/.tflite (openWakeWord)
│       ├── alexa.json/.tflite
│       ├── hey_luna.json/.tflite
│       └── stop.json/.tflite   # Stop word detection
├── sounds/                     # Sound effect files (auto-download)
│   ├── wake_word_triggered.flac
│   └── timer_finished.flac
├── pyproject.toml              # Project configuration
├── README.md                   # Documentation
├── changelog.json              # Version changelog
└── PROJECT_PLAN.md             # Project plan
```

## Dependencies

```toml
dependencies = [
    # Reachy Mini SDK (provides audio via media system)
    "reachy-mini",

    # Audio processing (fallback when not on Reachy Mini)
    "sounddevice>=0.5.0",
    "soundfile>=0.13.0",
    "numpy>=2.0.0",

    # Camera streaming
    "opencv-python>=4.10.0",

    # Wake word detection (local)
    "pymicro-wakeword>=2.0.0,<3.0.0",
    "pyopen-wakeword>=1.0.0,<2.0.0",

    # ESPHome protocol (communication with Home Assistant)
    "aioesphomeapi>=43.10.1",
    "zeroconf>=0.140.0",

    # Motion control (head movements)
    "scipy>=1.14.0",

    # Face tracking (YOLO-based head detection)
    "ultralytics>=8.3.0",
    "supervision>=0.25.0",
    "huggingface_hub>=0.27.0",

    # Sendspin synchronized audio (optional, for multi-room playback)
    "aiosendspin>=2.0.1",

    # Gesture detection (ONNX runtime for HaGRID models)
    "onnxruntime>=1.18.0",
]
```

## Usage Flow

1. **Install App**
   - Install `reachy_mini_ha_voice` from Reachy Mini App Store

2. **Start App**
   - App auto-starts ESPHome server (port 6053)
   - Auto-downloads required models and sounds

3. **Connect Home Assistant**
   - Home Assistant auto-discovers device (mDNS)
   - Or manually add: Settings → Devices & Services → Add Integration → ESPHome

4. **Use Voice Assistant**
   - Say "Okay Nabu" to wake
   - Speak command
   - Reachy Mini provides motion feedback

## ESPHome Entity Planning

Based on deep analysis of Reachy Mini SDK, the following entities are exposed to Home Assistant:

### Implemented Entities

| Entity Type | Name | Description |
|-------------|------|-------------|
| Media Player | `media_player` | Audio playback control |
| Voice Assistant | `voice_assistant` | Voice assistant pipeline |

### Implemented Control Entities (Read/Write)

#### Phase 1-3: Basic Controls and Pose

| ESPHome Entity Type | Name | SDK API | Range/Options | Description |
|---------------------|------|---------|---------------|-------------|
| `Number` | `speaker_volume` | `AudioPlayer.set_volume()` | 0-100 | Speaker volume |
| `Select` | `motor_mode` | `set_motor_control_mode()` | enabled/disabled/gravity_compensation | Motor mode selection |
| `Switch` | `motors_enabled` | `enable_motors()` / `disable_motors()` | on/off | Motor torque switch |
| `Button` | `wake_up` | `mini.wake_up()` | - | Wake robot action |
| `Button` | `go_to_sleep` | `mini.goto_sleep()` | - | Sleep robot action |
| `Number` | `head_x` | `goto_target(head=...)` | ±50mm | Head X position control |
| `Number` | `head_y` | `goto_target(head=...)` | ±50mm | Head Y position control |
| `Number` | `head_z` | `goto_target(head=...)` | ±50mm | Head Z position control |
| `Number` | `head_roll` | `goto_target(head=...)` | -40° ~ +40° | Head roll angle control |
| `Number` | `head_pitch` | `goto_target(head=...)` | -40° ~ +40° | Head pitch angle control |
| `Number` | `head_yaw` | `goto_target(head=...)` | -180° ~ +180° | Head yaw angle control |
| `Number` | `body_yaw` | `goto_target(body_yaw=...)` | -160° ~ +160° | Body yaw angle control |
| `Number` | `antenna_left` | `goto_target(antennas=...)` | -90° ~ +90° | Left antenna angle control |
| `Number` | `antenna_right` | `goto_target(antennas=...)` | -90° ~ +90° | Right antenna angle control |

#### Phase 4: Gaze Control

| ESPHome Entity Type | Name | SDK API | Range/Options | Description |
|---------------------|------|---------|---------------|-------------|
| `Number` | `look_at_x` | `look_at_world(x, y, z)` | World coordinates | Gaze point X coordinate |
| `Number` | `look_at_y` | `look_at_world(x, y, z)` | World coordinates | Gaze point Y coordinate |
| `Number` | `look_at_z` | `look_at_world(x, y, z)` | World coordinates | Gaze point Z coordinate |


### Implemented Sensor Entities (Read-only)

#### Phase 1 & 5: Basic Status and Audio Sensors

| ESPHome Entity Type | Name | SDK API | Description |
|---------------------|------|---------|-------------|
| `Text Sensor` | `daemon_state` | `DaemonStatus.state` | Daemon status |
| `Binary Sensor` | `backend_ready` | `backend_status.ready` | Backend ready status |
| `Text Sensor` | `error_message` | `DaemonStatus.error` | Current error message |
| `Sensor` | `doa_angle` | `DoAInfo.angle` | Sound source direction angle (°) |
| `Binary Sensor` | `speech_detected` | `DoAInfo.speech_detected` | Speech detection status |

#### Phase 6: Diagnostic Information

| ESPHome Entity Type | Name | SDK API | Description |
|---------------------|------|---------|-------------|
| `Sensor` | `control_loop_frequency` | `control_loop_stats` | Control loop frequency (Hz) |
| `Text Sensor` | `sdk_version` | `DaemonStatus.version` | SDK version |
| `Text Sensor` | `robot_name` | `DaemonStatus.robot_name` | Robot name |
| `Binary Sensor` | `wireless_version` | `DaemonStatus.wireless_version` | Wireless version flag |
| `Binary Sensor` | `simulation_mode` | `DaemonStatus.simulation_enabled` | Simulation mode flag |
| `Text Sensor` | `wlan_ip` | `DaemonStatus.wlan_ip` | Wireless IP address |

#### Phase 7: IMU Sensors (Wireless version only)

| ESPHome Entity Type | Name | SDK API | Description |
|---------------------|------|---------|-------------|
| `Sensor` | `imu_accel_x` | `mini.imu["accelerometer"][0]` | X-axis acceleration (m/s²) |
| `Sensor` | `imu_accel_y` | `mini.imu["accelerometer"][1]` | Y-axis acceleration (m/s²) |
| `Sensor` | `imu_accel_z` | `mini.imu["accelerometer"][2]` | Z-axis acceleration (m/s²) |
| `Sensor` | `imu_gyro_x` | `mini.imu["gyroscope"][0]` | X-axis angular velocity (rad/s) |
| `Sensor` | `imu_gyro_y` | `mini.imu["gyroscope"][1]` | Y-axis angular velocity (rad/s) |
| `Sensor` | `imu_gyro_z` | `mini.imu["gyroscope"][2]` | Z-axis angular velocity (rad/s) |
| `Sensor` | `imu_temperature` | `mini.imu["temperature"]` | IMU temperature (°C) |

#### Phase 8-12: Extended Features

| ESPHome Entity Type | Name | Description |
|---------------------|------|-------------|
| `Select` | `emotion` | Emotion selector (Happy/Sad/Angry/Fear/Surprise/Disgust) |
| `Number` | `microphone_volume` | Microphone volume (0-100%) |
| `Camera` | `camera` | ESPHome Camera entity (live preview) |
| `Number` | `led_brightness` | LED brightness (0-100%) |
| `Select` | `led_effect` | LED effect (off/solid/breathing/rainbow/doa) |
| `Number` | `led_color_r` | LED red component (0-255) |
| `Number` | `led_color_g` | LED green component (0-255) |
| `Number` | `led_color_b` | LED blue component (0-255) |
| `Switch` | `agc_enabled` | Auto gain control switch |
| `Number` | `agc_max_gain` | AGC max gain (0-30 dB) |
| `Number` | `noise_suppression` | Noise suppression level (0-100%) |
| `Binary Sensor` | `echo_cancellation_converged` | Echo cancellation convergence status |

> **Note**: Head position (x/y/z) and angles (roll/pitch/yaw), body yaw, antenna angles are all **controllable** entities,
> using `Number` type for bidirectional control. Call `goto_target()` when setting new values, call `get_current_head_pose()` etc. when reading current values.

### Implementation Priority

1. **Phase 1 - Basic Status and Volume** (High Priority) ✅ **Completed**
   - [x] `daemon_state` - Daemon status sensor
   - [x] `backend_ready` - Backend ready status
   - [x] `error_message` - Error message
   - [x] `speaker_volume` - Speaker volume control

2. **Phase 2 - Motor Control** (High Priority) ✅ **Completed**
   - [x] `motors_enabled` - Motor switch
   - [x] `motor_mode` - Motor mode selection (enabled/disabled/gravity_compensation)
   - [x] `wake_up` / `go_to_sleep` - Wake/sleep buttons

3. **Phase 3 - Pose Control** (Medium Priority) ✅ **Completed**
   - [x] `head_x/y/z` - Head position control
   - [x] `head_roll/pitch/yaw` - Head angle control
   - [x] `body_yaw` - Body yaw angle control
   - [x] `antenna_left/right` - Antenna angle control

4. **Phase 4 - Gaze Control** (Medium Priority) ✅ **Completed**
   - [x] `look_at_x/y/z` - Gaze point coordinate control

5. **Phase 5 - DOA (Direction of Arrival)** ✅ **Re-added for wakeup turn-to-sound**
   - [x] `doa_angle` - Sound source direction (degrees, 0-180°, where 0°=left, 90°=front, 180°=right)
   - [x] `speech_detected` - Speech detection status
   - [x] Turn-to-sound at wakeup (robot turns toward speaker when wake word detected)
   - [x] Direction correction: `yaw = π/2 - doa` (fixed left/right inversion)
   - Note: DOA only read once at wakeup to avoid daemon pressure; face tracking takes over after

6. **Phase 6 - Diagnostic Information** (Low Priority) ✅ **Completed**
   - [x] `control_loop_frequency` - Control loop frequency
   - [x] `sdk_version` - SDK version
   - [x] `robot_name` - Robot name
   - [x] `wireless_version` - Wireless version flag
   - [x] `simulation_mode` - Simulation mode flag
   - [x] `wlan_ip` - Wireless IP address

7. **Phase 7 - IMU Sensors** (Optional, wireless version only) ✅ **Completed**
   - [x] `imu_accel_x/y/z` - Accelerometer
   - [x] `imu_gyro_x/y/z` - Gyroscope
   - [x] `imu_temperature` - IMU temperature

8. **Phase 8 - Emotion Control** ✅ **Completed**
   - [x] `emotion` - Emotion selector (Happy/Sad/Angry/Fear/Surprise/Disgust)

9. **Phase 9 - Audio Control** ✅ **Completed**
   - [x] `microphone_volume` - Microphone volume control (0-100%)

10. **Phase 10 - Camera Integration** ✅ **Completed**
    - [x] `camera` - ESPHome Camera entity (live preview)

11. **Phase 11 - LED Control** ❌ **Disabled (LEDs hidden inside robot)**
    - [ ] `led_brightness` - LED brightness (0-100%) - Commented out
    - [ ] `led_effect` - LED effect (off/solid/breathing/rainbow/doa) - Commented out
    - [ ] `led_color_r/g/b` - LED RGB color (0-255) - Commented out

12. **Phase 12 - Audio Processing Parameters** ✅ **Completed**
    - [x] `agc_enabled` - Auto gain control switch
    - [x] `agc_max_gain` - AGC max gain (0-30 dB)
    - [x] `noise_suppression` - Noise suppression level (0-100%)
    - [x] `echo_cancellation_converged` - Echo cancellation convergence status (read-only)

13. **Phase 13 - Sendspin Audio Playback Support** ✅ **Completed**
    - [x] `sendspin_enabled` - Sendspin switch (Switch)
    - [x] `sendspin_url` - Sendspin server URL (Text Sensor)
    - [x] `sendspin_connected` - Sendspin connection status (Binary Sensor)
    - [x] AudioPlayer integrates aiosendspin library
    - [x] TTS audio sent to both local speaker and Sendspin server

14. **Phase 22 - Gesture Detection** ✅ **Completed**
    - [x] `gesture_detected` - Detected gesture name (Text Sensor)
    - [x] `gesture_confidence` - Gesture detection confidence % (Sensor)
    - [x] HaGRID ONNX models: hand_detector.onnx + crops_classifier.onnx
    - [x] Real-time state push to Home Assistant
    - [x] 18 supported gestures:
      | Gesture | Emoji | Gesture | Emoji |
      |---------|-------|---------|-------|
      | call | 🤙 | like | 👍 |
      | dislike | 👎 | mute | 🤫 |
      | fist | ✊ | ok | 👌 |
      | four | 🖐️ | one | ☝️ |
      | palm | ✋ | peace | ✌️ |
      | peace_inverted | 🔻✌️ | rock | 🤘 |
      | stop | 🛑 | stop_inverted | 🔻🛑 |
      | three | 3️⃣ | three2 | 🤟 |
      | two_up | ✌️☝️ | two_up_inverted | 🔻✌️☝️ |

---

## 🎉 Phase 1-13 + Phase 22 Entities Completed!

**Total Completed: 45 entities**
- Phase 1: 4 entities (Basic status and volume)
- Phase 2: 4 entities (Motor control)
- Phase 3: 9 entities (Pose control)
- Phase 4: 3 entities (Gaze control)
- Phase 5: 2 entities (Audio sensors)
- Phase 6: 6 entities (Diagnostic information)
- Phase 7: 7 entities (IMU sensors)
- Phase 8: 1 entity (Emotion control)
- Phase 9: 1 entity (Microphone volume)
- Phase 10: 1 entity (Camera)
- Phase 11: 0 entities (LED control - Disabled)
- Phase 12: 4 entities (Audio processing parameters)
- Phase 13: 3 entities (Sendspin audio output)
- Phase 22: 2 entities (Gesture detection)


---

## 🚀 Voice Assistant Enhancement Features Implementation Status

### Phase 14 - Emotion Action Feedback System (Enhanced) ✅

**Implementation Status**: Full keyword-based emotion detection implemented with 280+ Chinese/English keywords mapped to 35 emotion categories

**Implemented Features**:
- ✅ Phase 8 Emotion Selector entity (`emotion`)
- ✅ Basic emotion action playback API (`_play_emotion`)
- ✅ Emotion mapping: Happy/Sad/Angry/Fear/Surprise/Disgust
- ✅ Integration with HuggingFace action library (`pollen-robotics/reachy-mini-emotions-library`)
- ✅ SpeechSway system for natural head micro-movements during conversation (non-blocking)
- ✅ Tap detection disabled during emotion playback (polls daemon API for completion)
- ✅ **NEW (v0.8.0)**: Comprehensive emotion keyword detection from conversation text
- ✅ **NEW (v0.8.0)**: 280+ Chinese and English keywords mapped to 35 emotion categories
- ✅ **NEW (v0.8.0)**: Auto-trigger expressions based on text patterns in LLM responses

**Emotion Keyword Categories (v0.8.0)**:

| Expression ID | Category | Chinese Keywords | English Keywords |
|---------------|----------|------------------|------------------|
| `cheerful1` | Happy | 太棒了、开心、高兴 | great, awesome, happy |
| `laughing1` | Laughing | 哈哈、笑死、好笑 | haha, lol, funny |
| `enthusiastic1` | Excited | 兴奋、激动、耶 | excited, yay, cool |
| `amazed1` | Amazed | 神奇、厉害、牛 | amazing, incredible |
| `surprised1` | Surprised | 哇、天啊、真的吗 | wow, omg, really |
| `loving1` | Love | 爱、喜欢、可爱 | love, cute, adore |
| `grateful1` | Grateful | 谢谢、感谢 | thanks, appreciate |
| `welcoming1` | Welcome | 欢迎、你好 | hello, welcome |
| `helpful1` | Helpful | 当然、好的、没问题 | sure, of course |
| `curious1` | Curious | 好奇、有趣 | curious, interesting |
| `thoughtful1` | Thinking | 嗯、让我想想 | hmm, let me think |
| `sad1` | Sad | 难过、伤心、可惜 | sad, unfortunately |
| `oops1` | Oops | 抱歉、糟糕、哎呀 | sorry, oops |
| `confused1` | Confused | 困惑、搞不懂 | confused, puzzled |
| `fear1` | Fear | 害怕、可怕 | afraid, scared |
| `rage1` | Angry | 生气、愤怒 | angry, mad |
| `yes1` | Yes | 是的、对、没错 | yes, correct |
| `no1` | No | 不是、不行 | no, wrong |
| ... | ... | ... | ... |

**Design Decisions**:
- 🎯 No auto-play of full emotion actions during conversation to avoid blocking
- 🎯 Use voice-driven head sway (SpeechSway) for natural motion feedback
- 🎯 Emotion actions retained as manual trigger feature via ESPHome entity
- 🎯 Tap detection waits for actual move completion via `/api/move/running` polling
- 🎯 **NEW**: Keyword detection is case-insensitive and configurable via JSON

**Partially Implemented**:
- 🟡 Intent recognition and emotion matching (basic keyword matching implemented)
- ❌ Dance action library integration
- ❌ Context awareness (e.g., weather query - sunny plays happy, rainy plays sad)

**Code Locations**:
- `animations/emotion_keywords.json` - **NEW**: Emotion keyword mapping configuration (280+ keywords)
- `entity_registry.py:633-658` - Emotion Selector entity
- `satellite.py:_load_emotion_keywords()` - Load emotion keywords from JSON
- `satellite.py:_detect_and_play_emotion()` - Auto-detect emotions from text
- `satellite.py:_play_emotion()` - Emotion playback with move UUID tracking
- `satellite.py:_wait_for_move_completion()` - Polls daemon API for move completion
- `motion.py:132-156` - Conversation start motion control (uses SpeechSway)
- `movement_manager.py:541-595` - Move queue management (allows SpeechSway overlay)

**Actual Behavior**:

| Voice Assistant Event | Actual Action | Implementation Status |
|----------------------|---------------|----------------------|
| Wake word detected | Turn toward sound source + nod confirmation | ✅ Implemented |
| Conversation start | Voice-driven head micro-movements (SpeechSway) | ✅ Implemented |
| During conversation | Continuous voice-driven micro-movements + breathing animation | ✅ Implemented |
| Conversation end | Return to neutral position + breathing animation | ✅ Implemented |
| Manual emotion trigger | Play via ESPHome `emotion` entity | ✅ Implemented |

**Technical Details**:
```python
# motion.py - Use SpeechSway instead of full emotion actions during conversation
def on_speaking_start(self):
    self._is_speaking = True
    self._movement_manager.set_state(RobotState.SPEAKING)
    # SpeechSway automatically generates natural head micro-movements based on audio loudness
    # No full emotion actions played to avoid blocking conversation experience

# movement_manager.py - Motion layering system
# 1. Move queue (emotion actions) - Sets base pose
# 2. Action (nod/shake etc.) - Overlays on base pose
# 3. SpeechSway - Voice-driven micro-movements, can coexist with Move
# 4. Breathing - Idle breathing animation
```

**Original Plan** (Decided not to implement to avoid blocking conversation):

| Voice Assistant Event | Original Planned Action | Reason Not Implemented |
|----------------------|------------------------|------------------------|
| Positive response received | Play "happy" action | Full action would block conversation fluency |
| Negative response received | Play "sad" action | Full action would block conversation fluency |
| Play music/entertainment | Play "dance" action | Full action would block conversation fluency |
| Timer completed | Play "alert" action | Full action would block conversation fluency |
| Error/cannot understand | Play "confused" action | Full action would block conversation fluency |

**Manual Emotion Trigger Example**:
```yaml
# Home Assistant automation example - Manual emotion trigger
automation:
  - alias: "Reachy Good Morning Greeting"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: select.select_option
        target:
          entity_id: select.reachy_mini_emotion
        data:
          option: "Happy"
```

### Phase 15 - Face Tracking (Complements DOA Turn-to-Sound) ✅ **Completed**

**Goal**: Implement natural face tracking so robot looks at speaker during conversation.

**Design Decision**:
- ✅ DOA (Direction of Arrival): Used once at wakeup to turn toward sound source
- ✅ YOLO face detection: Takes over after initial turn for continuous tracking
- ✅ Body follows head rotation: Body yaw automatically syncs with head yaw for natural tracking
- Reason: DOA provides quick initial orientation, face tracking provides accurate continuous tracking, body following enables natural whole-body tracking similar to human behavior

**Wakeup Turn-to-Sound Flow**:
1. Wake word detected → Read DOA angle once (avoid daemon pressure)
2. If DOA angle > 10°: Turn head toward sound source (80% of angle, conservative)
3. Face tracking takes over for continuous tracking during conversation

**Implemented Features**:

| Feature | Description | Implementation Location | Status |
|---------|-------------|------------------------|--------|
| DOA turn-to-sound | Turn toward speaker at wakeup | `satellite.py:_turn_to_sound_source()` | ✅ Implemented |
| YOLO face detection | Uses `AdamCodd/YOLOv11n-face-detection` model | `head_tracker.py` | ✅ Implemented |
| Adaptive frame rate tracking | 15fps during conversation, 2fps when idle without face | `camera_server.py` | ✅ Implemented |
| look_at_image() | Calculate target pose from face position | `camera_server.py` | ✅ Implemented |
| Smooth return to neutral | Smooth return within 1 second after face lost | `camera_server.py` | ✅ Implemented |
| face_tracking_offsets | As secondary pose overlay to motion control | `movement_manager.py` | ✅ Implemented |
| Body follows head rotation | Body yaw syncs with head yaw extracted from final pose matrix | `movement_manager.py:_compose_final_pose()` | ✅ Implemented (v0.8.3) |
| DOA entities | `doa_angle` and `speech_detected` exposed to Home Assistant | `entity_registry.py` | ✅ Implemented |
| face_detected entity | Binary sensor for face detection state | `entity_registry.py` | ✅ Implemented |
| Model download retry | 3 retries, 5 second interval | `head_tracker.py` | ✅ Implemented |
| Conversation mode integration | Auto-switch tracking frequency on voice assistant state change | `satellite.py` | ✅ Implemented |

**Resource Optimization (v0.5.1, updated v0.6.2)**:
- During conversation (listening/thinking/speaking): High-frequency tracking 15fps
- Idle with face detected: High-frequency tracking 15fps
- Idle without face for 5s: Low-power mode 2fps
- Idle without face for 30s: Ultra-low power mode 0.5fps (every 2 seconds)
- Gesture detection only runs when face detected recently (within 5s)
- Immediately restore high-frequency tracking when face detected

**Code Locations**:
- `satellite.py:_turn_to_sound_source()` - DOA turn-to-sound at wakeup
- `head_tracker.py` - YOLO face detector (`HeadTracker` class)
- `camera_server.py:_capture_frames()` - Adaptive frame rate face tracking
- `camera_server.py:set_conversation_mode()` - Conversation mode switch API
- `satellite.py:_set_conversation_mode()` - Voice assistant state integration
- `movement_manager.py:set_face_tracking_offsets()` - Face tracking offset API
- `movement_manager.py:_compose_final_pose()` - Body yaw follows head yaw (v0.8.3)

**Technical Details**:
```python
# camera_server.py - Adaptive frame rate face tracking
class MJPEGCameraServer:
    def __init__(self):
        self._fps_high = 15  # During conversation/face detected
        self._fps_low = 2    # Idle without face (5-30s)
        self._fps_idle = 0.5 # Ultra-low power (>30s without face)
        self._low_power_threshold = 5.0   # 5s without face switches to low power
        self._idle_threshold = 30.0       # 30s without face switches to idle mode

    def _should_run_ai_inference(self, current_time):
        # Conversation mode: Always high-frequency tracking
        if self._in_conversation:
            return True
        # High-frequency mode: Track every frame
        if self._current_fps == self._fps_high:
            return True
        # Low/idle power mode: Periodic detection
        return time.since_last_check >= 1/self._current_fps

# satellite.py - Voice assistant state integration
def _reachy_on_listening(self):
    self._set_conversation_mode(True)  # Start conversation, high-frequency tracking

def _reachy_on_idle(self):
    self._set_conversation_mode(False)  # End conversation, adaptive tracking

# movement_manager.py - Body follows head rotation (v0.8.3)
# This enables natural body rotation when tracking faces, similar to how
# the reference project's sweep_look tool synchronizes body_yaw with head_yaw.
def _compose_final_pose(self) -> Tuple[np.ndarray, Tuple[float, float], float]:
    # ... compose head pose from all motion sources ...

    # Extract yaw from final head pose rotation matrix
    # The rotation matrix uses xyz euler convention
    final_rotation = R.from_matrix(final_head[:3, :3])
    _, _, final_head_yaw = final_rotation.as_euler('xyz')

    # Body follows head yaw directly
    # SDK's automatic_body_yaw (inverse_kinematics_safe) only handles collision
    # prevention by clamping relative angle to max 65°, not active following
    body_yaw = final_head_yaw

    return final_head, (antenna_right, antenna_left), body_yaw
```

**Body Following Head Rotation (v0.8.3)**:
- SDK's `automatic_body_yaw` is only **collision protection**, not active body following
- The `inverse_kinematics_safe` function with `max_relative_yaw=65°` only prevents head-body collision
- To enable natural body following, `body_yaw` must be explicitly set to match `head_yaw`
- Body yaw is extracted from final head pose matrix using scipy's `R.from_matrix().as_euler('xyz')`
- This matches the reference project's `sweep_look.py` behavior where `target_body_yaw = head_yaw`


### Phase 16 - Cartoon Style Motion Mode (Partial) 🟡

**Goal**: Use SDK interpolation techniques for more expressive robot movements.

**SDK Support**: `InterpolationTechnique` enum
- `LINEAR` - Linear, mechanical feel
- `MIN_JERK` - Minimum jerk, natural and smooth (default)
- `EASE_IN_OUT` - Ease in-out, elegant
- `CARTOON` - Cartoon style, with bounce effect, lively and cute

**Implemented Features**:
- ✅ 100Hz unified control loop (`movement_manager.py`) - Restored to 100Hz after daemon update
- ✅ JSON-driven animation system (`AnimationPlayer`) - Inspired by SimpleDances project
- ✅ Conversation state animations (idle/listening/thinking/speaking)
- ✅ Pose change detection - Only send commands on significant changes (threshold 0.005)
- ✅ State query caching - 2s TTL, reduces daemon load
- ✅ Smooth interpolation (ease in-out curve)
- ✅ Command queue mode - Thread-safe external API
- ✅ Error throttling - Prevents log explosion
- ✅ Connection health monitoring - Auto-detect and recover from connection loss

**Animation System (v0.5.13)**:
- `AnimationPlayer` class loads animations from `conversation_animations.json`
- Each animation defines: pitch/yaw/roll amplitudes, position offsets, antenna movements, frequency
- Smooth transitions between animations (configurable duration)
- State-to-animation mapping: idle→idle, listening→listening, thinking→thinking, speaking→speaking

**Not Implemented**:
- ❌ Dynamic interpolation technique switching (CARTOON/EASE_IN_OUT etc.)
- ❌ Exaggerated cartoon bounce effects

**Code Locations**:
- `animation_player.py` - AnimationPlayer class
- `animations/conversation_animations.json` - Animation definitions
- `movement_manager.py` - 100Hz control loop with animation integration

**Scene Implementation Status**:

| Scene | Recommended Interpolation | Effect | Status |
|-------|--------------------------|--------|--------|
| Wake nod | `CARTOON` | Lively bounce effect | ❌ Not implemented |
| Thinking head up | `EASE_IN_OUT` | Elegant transition | ✅ Implemented (smooth interpolation) |
| Speaking micro-movements | `MIN_JERK` | Natural and fluid | ✅ Implemented (SpeechSway) |
| Error head shake | `CARTOON` | Exaggerated denial | ❌ Not implemented |
| Return to neutral | `MIN_JERK` | Smooth return | ✅ Implemented |
| Idle breathing | - | Subtle sense of life | ✅ Implemented (BreathingAnimation) |

### Phase 17 - Antenna Sync Animation During Speech (Completed) ✅

**Goal**: Antennas sway with audio rhythm during TTS playback, simulating "speaking" effect.

**Implemented Features**:
- ✅ JSON-driven animation system with antenna movements
- ✅ Different antenna patterns: "both" (sync), "wiggle" (opposite phase)
- ✅ State-specific antenna animations (listening/thinking/speaking)
- ✅ Smooth transitions between animation states

**Code Locations**:
- `animation_player.py` - AnimationPlayer with antenna offset calculation
- `animations/conversation_animations.json` - Antenna amplitude and pattern definitions
- `movement_manager.py` - Antenna offset composition in final pose

### Phase 18 - Visual Gaze Interaction (Not Implemented) ❌

**Goal**: Use camera to detect faces for eye contact.

**SDK Support**:
- `look_at_image(u, v)` - Look at point in image
- `look_at_world(x, y, z)` - Look at world coordinate point
- `media.get_frame()` - Get camera frame (✅ Already implemented in `camera_server.py:146`)

**Not Implemented Features**:

| Feature | Description | Status |
|---------|-------------|--------|
| Face detection | Use OpenCV/MediaPipe to detect faces | ❌ Not implemented |
| Eye tracking | Look at speaker's face during conversation | ❌ Not implemented |
| Multi-person switching | When multiple people detected, look at current speaker | ❌ Not implemented |
| Idle scanning | Randomly look around when idle | ❌ Not implemented |

### Phase 19 - Gravity Compensation Interactive Mode (Partial) 🟡

**Goal**: Allow users to physically touch and guide robot head for "teaching" style interaction.

**SDK Support**: `enable_gravity_compensation()` - Motors enter gravity compensation mode, can be manually moved

**Implemented Features**:
- ✅ Gravity compensation mode switch (`motor_mode` Select entity, option "gravity_compensation")
- ✅ `reachy_controller.py:236-237` - Gravity compensation API call

**Not Implemented**:
- ❌ Teaching mode - Record motion trajectory
- ❌ Save/playback custom actions
- ❌ Voice command triggered teaching flow

**Application Scenarios**:
- ❌ User says "Let me teach you a move" → Enter gravity compensation mode
- ❌ User manually moves head → Record motion trajectory
- ❌ User says "Remember this" → Save action
- ❌ User says "Do that action again" → Playback recorded action

### Phase 20 - Environment Awareness Response (Partial) 🟡

**Goal**: Use IMU sensors to sense environment changes and respond.

**SDK Support**:
- ✅ `mini.imu["accelerometer"]` - Accelerometer (Phase 7 implemented as entity)
- ✅ `mini.imu["gyroscope"]` - Gyroscope (Phase 7 implemented as entity)

**Implemented Features**:

| Feature | Description | Status |
|---------|-------------|--------|
| Continuous conversation | Controlled via Home Assistant switch | ✅ Implemented |
| IMU sensor entities | Accelerometer and gyroscope exposed to HA | ✅ Implemented |

> **Note**: Tap-to-wake feature was removed in v0.5.16 due to false triggers from robot movement. Continuous conversation is now controlled via Home Assistant switch.

**Not Implemented**:

| Detection Event | Response Action | Status |
|-----------------|-----------------|--------|
| Being shaken | Play dizzy action + voice "Don't shake me~" | ❌ Not implemented |
| Tilted/fallen | Play help action + voice "I fell, help me" | ❌ Not implemented |
| Long idle | Enter sleep animation | ❌ Not implemented |

### Phase 21 - Home Assistant Scene Integration (Not Implemented) ❌

**Goal**: Trigger robot actions based on Home Assistant scenes/automations.

**Implementation**: Via ESPHome service calls

**Not Implemented Scenes**:

| HA Scene | Robot Response | Status |
|----------|----------------|--------|
| Good morning scene | Play wake action + "Good morning!" | ❌ Not implemented |
| Good night scene | Play sleep action + "Good night~" | ❌ Not implemented |
| Someone home | Turn toward door + wave + "Welcome home!" | ❌ Not implemented |
| Doorbell rings | Turn toward door + alert action | ❌ Not implemented |
| Play music | Sway with music rhythm | ❌ Not implemented |


---

## 📊 Feature Implementation Summary

### ✅ Completed Features

#### Core Voice Assistant (Phase 1-12)
- **40+ ESPHome entities** - All implemented (Phase 11 LED disabled)
- **Basic voice interaction** - Wake word detection (microWakeWord/openWakeWord), STT/TTS integration
- **Motion feedback** - Nod, shake, gaze and other basic actions
- **Audio processing** - AGC, noise suppression, echo cancellation
- **Camera stream** - MJPEG live preview with ESPHome Camera entity

#### Extended Features (Phase 13-22)
- **Phase 13** ✅ - Sendspin multi-room audio support
- **Phase 14** ✅ - Emotion keyword detection (280+ keywords, 35 categories)
- **Phase 15** ✅ - Face tracking with body following (DOA + YOLO + body_yaw sync)
- **Phase 16** ✅ - JSON-driven animation system (100Hz control loop)
- **Phase 17** ✅ - Antenna sync animation during speech
- **Phase 22** ✅ - Gesture detection (HaGRID ONNX, 18 gestures)

### 🟡 Partially Implemented Features

- **Phase 19** - Gravity compensation mode switch (teaching flow not implemented)
- **Phase 20** - IMU sensor entities (trigger logic not implemented)

### ❌ Not Implemented Features

- **Phase 18** - Visual gaze interaction (eye contact with multiple people)
- **Phase 21** - Home Assistant scene integration (morning/night routines)

---

## Feature Priority Summary (Updated v0.8.3)

### Completed ✅
- ✅ **Phase 1-12**: Core ESPHome entities and voice assistant
- ✅ **Phase 13**: Sendspin audio playback
- ✅ **Phase 14**: Emotion keyword detection and auto-trigger
- ✅ **Phase 15**: Face tracking with body following
- ✅ **Phase 16**: JSON-driven animation system
- ✅ **Phase 17**: Antenna sync animation
- ✅ **Phase 22**: Gesture detection

### Partial 🟡
- 🟡 **Phase 19**: Gravity compensation mode (teaching flow pending)
- 🟡 **Phase 20**: Environment awareness (IMU entities done, triggers pending)

### Not Implemented ❌
- ❌ **Phase 18**: Visual gaze interaction
- ❌ **Phase 21**: Home Assistant scene integration

---

## 📈 Completion Statistics

| Phase | Status | Completion | Notes |
|-------|--------|------------|-------|
| Phase 1-12 | ✅ Complete | 100% | 40 ESPHome entities implemented (Phase 11 LED disabled) |
| Phase 13 | ✅ Complete | 100% | Sendspin audio playback support |
| Phase 14 | ✅ Complete | 95% | Emotion keyword detection with 280+ keywords, 35 categories |
| Phase 15 | ✅ Complete | 100% | Face tracking with DOA, YOLO detection, body follows head (v0.8.3) |
| Phase 16 | ✅ Complete | 100% | JSON-driven animation system (100Hz control loop) |
| Phase 17 | ✅ Complete | 100% | Antenna sync animation during speech |
| Phase 18 | ❌ Not done | 10% | Camera implemented, missing multi-person gaze |
| Phase 19 | 🟡 Partial | 40% | Gravity compensation mode switch, missing teaching flow |
| Phase 20 | 🟡 Partial | 30% | IMU sensors exposed, missing trigger logic |
| Phase 21 | ❌ Not done | 0% | Home Assistant scene integration not implemented |
| Phase 22 | ✅ Complete | 100% | Gesture detection with HaGRID ONNX models |

**Overall Completion**: **Phase 1-17 + 22: ~98%** | **Phase 18-21: ~20%**


---

## 🔧 Daemon Crash Fix (2025-01-05)

### Problem Description
During long-term operation, `reachy_mini daemon` would crash, causing robot to become unresponsive.

### Root Cause
1. **100Hz control loop too frequent** - Calling `robot.set_target()` every 10ms, even when pose hasn't changed
2. **Frequent state queries** - Every entity state read calls `get_status()`, `get_current_head_pose()` etc.
3. **Missing change detection** - Even when pose hasn't changed, continues sending same commands
4. **Zenoh message queue blocking** - Accumulated 150+ messages per second, daemon cannot process in time

### Fix Solution

#### 1. Control loop frequency (movement_manager.py)
```python
# Initially reduced from 100Hz to 20Hz, then later restored to 100Hz
# See "Update (2026-01-12)" below for current status
CONTROL_LOOP_FREQUENCY_HZ = 100  # Now restored to 100Hz
```

#### 2. Add pose change detection (movement_manager.py)
```python
# Only send commands on significant pose changes
if self._last_sent_pose is not None:
    max_diff = max(abs(pose[k] - self._last_sent_pose.get(k, 0.0)) for k in pose.keys())
    if max_diff < 0.001:  # Threshold: 0.001 rad or 0.001 m
        return  # Skip sending
```

#### 3. State query caching (reachy_controller.py)
```python
# Cache daemon status query results
self._cache_ttl = 0.1  # 100ms TTL
self._last_status_query = 0.0

def _get_cached_status(self):
    now = time.time()
    if now - self._last_status_query < self._cache_ttl:
        return self._state_cache.get('status')  # Use cache
    # ... query and update cache
```

#### 4. Head pose query caching (reachy_controller.py)
```python
# Cache get_current_head_pose() and get_current_joint_positions() results
def _get_cached_head_pose(self):
    # Reuse cached results within 100ms
```

### Fix Results

| Metric | Before Fix | After Fix | Improvement |
|--------|------------|-----------|-------------|
| Control message frequency | ~100 msg/s | ~20 msg/s | ↓ 80% |
| State query frequency | ~50 msg/s | ~5 msg/s | ↓ 90% |
| Total Zenoh messages | ~150 msg/s | ~25 msg/s | ↓ 83% |
| Daemon CPU load | Sustained high load | Normal load | Significantly reduced |
| Expected stability | Crash within hours | Stable for days | Major improvement |

### Related Files
- `DAEMON_CRASH_FIX_PLAN.md` - Detailed fix plan and test plan
- `movement_manager.py` - Control loop optimization
- `reachy_controller.py` - State query caching

### Future Optimization Suggestions
1. ⏳ Dynamic frequency adjustment - 50Hz during motion, 5Hz when idle
2. ⏳ Batch state queries - Get all states at once
3. ⏳ Performance monitoring and alerts - Real-time daemon health monitoring

---

## 🔧 Daemon Crash Deep Fix (2026-01-07)

> **Update (2026-01-12)**: After daemon updates and further testing, control loop frequency has been restored to 100Hz (same as `reachy_mini_conversation_app`). The pose change threshold (0.005) and state cache TTL (2s) optimizations remain in place to reduce unnecessary Zenoh messages.

### Problem Description
During long-term operation, `reachy_mini daemon` still crashes, previous fix not thorough enough.

### Root Cause Analysis

Through deep analysis of SDK source code:

1. **Each `set_target()` sends 3 Zenoh messages**
   - `set_target_head_pose()` - 1 message
   - `set_target_antenna_joint_positions()` - 1 message  
   - `set_target_body_yaw()` - 1 message

2. **Daemon control loop is 50Hz**
   - See `reachy_mini/daemon/backend/robot/backend.py`: `control_loop_frequency = 50.0`
   - If message send frequency exceeds 50Hz, daemon may not process in time

3. **Previous 20Hz control loop still too high**
   - 20Hz × 3 messages = 60 messages/second
   - Already exceeds daemon's 50Hz processing capacity

4. **Pose change threshold too small (0.002)**
   - Breathing animation, speech sway, face tracking continuously produce tiny changes
   - Almost every loop triggers `set_target()`

### Fix Solution

#### 1. Control loop frequency history (movement_manager.py)
```python
# Evolution: 100Hz -> 20Hz -> 10Hz -> 100Hz (restored)
# After daemon updates, 100Hz is now stable
CONTROL_LOOP_FREQUENCY_HZ = 100  # Restored to 100Hz (2026-01-12)
```

#### 2. Increase pose change threshold (movement_manager.py)
```python
# Increased from 0.002 to 0.005
# 0.005 rad ≈ 0.29 degrees, still smooth enough
self._pose_change_threshold = 0.005
```

#### 3. Reduce camera/face tracking frequency (camera_server.py)
```python
# Reduced from 15fps to 10fps
fps: int = 10
```

#### 4. Increase state cache TTL (reachy_controller.py)
```python
# Increased from 1 second to 2 seconds
self._cache_ttl = 2.0
```

### Fix Results

> **Note**: Control loop has been restored to 100Hz as of 2026-01-12. The table below shows historical values before restoration.

| Metric | Before (20Hz) | After (10Hz) | Current (100Hz) |
|--------|---------------|--------------|-----------------|
| Control loop frequency | 20 Hz | 10 Hz | 100 Hz (restored) |
| Max Zenoh messages | 60 msg/s | 30 msg/s | ~100 msg/s (optimized) |
| Actual messages (with change detection) | ~40 msg/s | ~15 msg/s | ~30 msg/s |
| Face tracking frequency | 15 Hz | 10 Hz | Adaptive (2-15 Hz) |
| State cache TTL | 1 second | 2 seconds | 2 seconds |
| Expected stability | Crash within hours | Stable operation | Stable (daemon updated) |

### Key Finding

Reference `reachy_mini_conversation_app` uses 100Hz control loop. After daemon updates and optimizations (pose change threshold 0.005, state cache TTL 2s), our app now also runs stably at 100Hz.

### Related Files
- `movement_manager.py` - Control loop frequency and pose threshold
- `camera_server.py` - Face tracking frequency
- `reachy_controller.py` - State cache TTL


---

## 🔧 Microphone Sensitivity Optimization (2026-01-07)

### Problem
Low microphone sensitivity - Need to be very close for voice recognition.

### Solution
Comprehensive ReSpeaker XVF3800 microphone optimization:

| Parameter | Default | Optimized | Notes |
|-----------|---------|-----------|-------|
| AGC | Off | On | Auto volume normalization |
| AGC max gain | ~15dB | 30dB | Better distant speech pickup |
| AGC target level | -25dB | -18dB | Stronger output signal |
| Microphone gain | 1.0x | 2.0x | Base gain doubled |
| Noise suppression | ~0.5 | 0.15 | Reduced speech mis-suppression |

### Result
Microphone sensitivity improved from ~30cm to ~2-3m effective range.

---

## 🔧 v0.5.1 Bug Fixes (2026-01-08)

### Issue 1: Music Not Resuming After Voice Conversation

**Fix**: Sendspin now connects to `music_player` instead of `tts_player`

### Issue 2: Audio Conflict During Voice Assistant Wakeup

**Fix**: Added `pause_sendspin()` and `resume_sendspin()` methods to `audio_player.py`

### Issue 3: Sendspin Sample Rate Optimization

**Fix**: Prioritize 16kHz in Sendspin supported formats (hardware limitation)

---

## 🔧 v0.5.15 Updates (2026-01-11)

### Feature 1: Audio Settings Persistence

AGC Enabled, AGC Max Gain, Noise Suppression settings now persist to `preferences.json`.

### Feature 2: Sendspin Discovery Refactoring

Moved mDNS discovery to `zeroconf.py` for better separation of concerns.


---

### SDK Data Structure Reference

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

# Full state
class FullState:
    control_mode: MotorControlMode
    head_pose: XYZRPYPose  # x, y, z (m), roll, pitch, yaw (rad)
    head_joints: list[float]  # 7 joint angles
    body_yaw: float
    antennas_position: list[float]  # [right, left]
    doa: DoAInfo  # angle (rad), speech_detected (bool)

# IMU data (wireless version only)
imu_data = {
    "accelerometer": [x, y, z],  # m/s²
    "gyroscope": [x, y, z],      # rad/s
    "quaternion": [w, x, y, z],  # Attitude quaternion
    "temperature": float         # °C
}

# Safety limits
HEAD_PITCH_ROLL_LIMIT = [-40°, +40°]
HEAD_YAW_LIMIT = [-180°, +180°]
BODY_YAW_LIMIT = [-160°, +160°]
YAW_DELTA_MAX = 65°  # Max difference between head and body yaw
```

### ESPHome Protocol Implementation Notes

ESPHome protocol communicates with Home Assistant via protobuf messages. The following message types need to be implemented:

```python
from aioesphomeapi.api_pb2 import (
    # Number entity (volume/angle control)
    ListEntitiesNumberResponse,
    NumberStateResponse,
    NumberCommandRequest,

    # Select entity (motor mode)
    ListEntitiesSelectResponse,
    SelectStateResponse,
    SelectCommandRequest,

    # Button entity (wake/sleep)
    ListEntitiesButtonResponse,
    ButtonCommandRequest,

    # Switch entity (motor switch)
    ListEntitiesSwitchResponse,
    SwitchStateResponse,
    SwitchCommandRequest,

    # Sensor entity (numeric sensors)
    ListEntitiesSensorResponse,
    SensorStateResponse,

    # Binary Sensor entity (boolean sensors)
    ListEntitiesBinarySensorResponse,
    BinarySensorStateResponse,

    # Text Sensor entity (text sensors)
    ListEntitiesTextSensorResponse,
    TextSensorStateResponse,
)
```

## Reference Projects

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)
- [pollen-robotics/reachy_mini](https://github.com/pollen-robotics/reachy_mini)
- [reachy_mini_conversation_app](https://github.com/pollen-robotics/reachy_mini_conversation_app)
- [sendspin-cli](https://github.com/Sendspin/sendspin-cli)
- [home-assistant-voice](https://github.com/esphome/home-assistant-voice-pe/blob/dev/home-assistant-voice.yaml)