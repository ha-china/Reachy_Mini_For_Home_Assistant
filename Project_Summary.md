# Reachy Mini for Home Assistant - Project Plan (Current snapshot: v1.0.0)

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
│  │  └──────────────┘   │ • Hardware DSP path available                │  │  │
│  │                     │ • App currently relies on HA STT/TTS         │  │  │
│  │                     │ • DOA/VAD used by the current runtime        │  │  │
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
│  │  MovementManager (50Hz Control Loop)                                  │  │
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
│  │  │ Body Following                                                │   │  │
│  │  │ • Body yaw syncs with head yaw for natural tracking            │   │  │
│  │  │ • Extracted from final head pose matrix                        │   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────── GESTURE DETECTION ────────────────────────┐  │
│  │  HaGRID ONNX Models + GestureSmoother (v1.0.0)                     │  │
│  │  • 18 gesture classes (call, like, dislike, fist, ok, palm, etc.)    │  │
│  │  • GestureSmoother fast-confirm + grace clear                        │  │
│  │  • Batch detection: all hands (not just highest confidence)         │  │
│  │  • Detection cadence: adaptive scheduler + minimum processing FPS    │  │
│  │  • No confidence filtering - all detections passed to Home Assistant│  │
│  │  • Runtime switchable (default OFF, model unloaded when disabled)    │  │
│  │  • Real-time state push to Home Assistant                            │  │
│  │  • No conflicts with face tracking (shared frame, independent)       │  │
│  │  • SDK integration: MediaBackend detection, proper resource cleanup │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────── ESPHOME SERVER ────────────────────────────┐  │
│  │  Port 6053 (mDNS auto-discovery)                                      │  │
│  │  • Entity count evolves by release (sensors, controls, media, camera) │  │
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

### Software Module Architecture (v1.0.0)

```
reachy_mini_home_assistant/
│
├── main.py                    # Application entry point
├── voice_assistant.py         # Voice assistant service orchestrator
├── reachy_controller.py       # Reachy Mini SDK wrapper
├── models.py                  # Data models
│
├── core/                      # Core Infrastructure
│   ├── config.py              # Centralized nested configuration
│   ├── service_base.py        # SleepAwareService base class
│   ├── sleep_manager.py       # Sleep/Wake lifecycle management
│   ├── daemon_monitor.py      # Daemon state monitoring
│   ├── health_monitor.py      # Service health checking
│   ├── memory_monitor.py      # Memory usage monitoring
│   ├── robot_state_monitor.py # Robot connection state monitoring
│   ├── system_diagnostics.py  # System diagnostics
│   ├── exceptions.py          # Custom exception classes
│   └── util.py                # Utility functions
│
├── motion/                    # Motion Control
│   ├── movement_manager.py    # 50Hz unified motion control loop
│   ├── antenna.py             # Antenna animation control
│   ├── pose_composer.py       # Pose composition from multiple sources
│   ├── gesture_actions.py     # Gesture → Robot action mapping
│   ├── smoothing.py           # Motion smoothing algorithms
│   ├── state_machine.py       # Robot state definitions
│   ├── animation_player.py    # Animation player
│   ├── emotion_moves.py       # Emotion moves
│   ├── speech_sway.py         # Speech-driven head micro-movements
│   └── reachy_motion.py       # Reachy motion API
│
├── vision/                    # Vision Processing
│   ├── camera_server.py       # MJPEG camera stream server
│   ├── head_tracker.py        # YOLO face detector
│   ├── gesture_detector.py    # HaGRID gesture detection
│   ├── gesture_smoother.py    # Gesture history tracking and confirmation (v1.0.0)
│   ├── face_tracking_interpolator.py  # Smooth face tracking
│   └── frame_processor.py     # Adaptive frame rate management
│
├── audio/                     # Audio runtime support
│   ├── audio_player.py        # TTS + Sendspin playback
│   ├── microphone.py          # Hardware audio helper / legacy tuning code
│   └── doa_tracker.py         # Direction of Arrival tracking
│
├── entities/                  # Home Assistant Entities
│   ├── entity.py              # ESPHome base entity
│   ├── entity_registry.py     # ESPHome entity registry
│   ├── entity_factory.py      # Entity creation factory
│   ├── entity_keys.py         # Entity key constants
│   ├── entity_extensions.py   # Extended entity types
│   ├── event_emotion_mapper.py # HA event → Emotion mapping
│   └── emotion_detector.py    # Disabled runtime path for text emotion detection
│
├── protocol/                  # Protocol Handling
│   ├── satellite.py           # ESPHome protocol handler
│   ├── api_server.py          # HTTP API server
│   └── zeroconf.py            # mDNS discovery
│
├── animations/               # Animation definitions
│   └── conversation_animations.json  # Unified built-in behavior resource file
│
└── wakewords/                # Wake word models
    ├── okay_nabu.json/.tflite
    ├── hey_jarvis.json/.tflite
    ├── alexa.json/.tflite
    ├── hey_luna.json/.tflite
    └── stop.json/.tflite
```


### Current Runtime Defaults (v1.0.0)

- `idle_behavior_enabled`: OFF
- `sendspin_enabled`: OFF
- `face_tracking_enabled`: OFF
- `gesture_detection_enabled`: OFF
- `face_confidence_threshold`: 0.5 (persistent)
- Idle antenna behavior: torque disabled in `IDLE`, re-enabled when leaving `IDLE`
- Voice phases and HA-triggered emotions are routed through one built-in zero-config behavior layer

When face/gesture switches are OFF, their models are unloaded to save resources.

### Current Audio Startup Note (SDK 1.4.1)

- On some boots, SDK media init may fall back to OpenAL (`gstopenalsrc`) and fail microphone capture if source card probing is not ready.
- App behavior in v1.0.0 is fail-fast for missing microphone capture to avoid silent degraded startup.
- This is tracked as an SDK/media backend startup readiness issue rather than an OpenAI pipeline issue.

### Latest Incremental Update (2026-03-04) - Viewer-Aware Camera Streaming

- MJPEG encoding/push is now viewer-aware: when no `/stream` client is connected, continuous MJPEG encoding is skipped to reduce CPU usage.
- Face tracking and gesture detection still run without active stream viewers, so AI behavior remains available.
- `/snapshot` now supports on-demand frame encode when no cached stream frame exists.
- Stream output no longer forces fixed 1080p/25fps; it follows camera backend defaults (resolution/FPS) and only falls back when backend FPS is unavailable.
- Transition from "watching" to "not watching" returns to adaptive idle pacing for resource saving.

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
- [x] YOLO face tracking (complements DOA wakeup orientation)
- [x] 50Hz unified motion control loop

### Application Architecture
- [x] Compliant with Reachy Mini App architecture



## File List

```
reachy_mini_ha_voice/
├── reachy_mini_ha_voice/
│   ├── __init__.py             # Package initialization (v0.9.9)
│   ├── __main__.py             # Command line entry
│   ├── main.py                 # ReachyMiniApp entry
│   ├── voice_assistant.py      # Voice assistant service (1270 lines)
│   ├── protocol/               # ESPHome protocol handling
│   │   ├── __init__.py         # Module exports (13 lines)
│   │   ├── satellite.py        # ESPHome protocol handler (1022 lines)
│   │   ├── api_server.py       # HTTP API server (172 lines)
│   │   └── zeroconf.py         # mDNS discovery
│   ├── models.py               # Data models
│   └── reachy_controller.py    # Reachy Mini controller wrapper (961 lines)
│   │
│   ├── core/                   # Core infrastructure modules
│   │   ├── __init__.py         # Module exports
│   │   ├── config.py           # Centralized configuration (368 lines)
│   │   ├── daemon_monitor.py   # Daemon state monitoring (377 lines)
│   │   ├── service_base.py     # SleepAwareService base class (552 lines)
│   │   ├── sleep_manager.py    # Sleep/Wake coordination (278 lines)
│   │   ├── health_monitor.py   # Service health checking (305 lines)
│   │   ├── memory_monitor.py   # Memory usage monitoring (282 lines)
│   │   ├── robot_state_monitor.py  # Robot connection state monitoring (300 lines)
│   │   ├── system_diagnostics.py   # System diagnostics (250 lines)
│   │   └── exceptions.py       # Custom exception classes (68 lines)
│   │   └── util.py             # Utility functions (28 lines)
│   │
│   ├── motion/                 # Motion control modules
│   │   ├── __init__.py         # Module exports
│   │   ├── antenna.py          # Antenna freeze/unfreeze control
│   │   ├── pose_composer.py    # Pose composition utilities
│   │   ├── gesture_actions.py  # Gesture to action mapping
│   │   ├── smoothing.py        # Smoothing/transition algorithms
│   │   ├── state_machine.py    # State machine definitions
│   │   ├── animation_player.py # Animation player
│   │   ├── emotion_moves.py    # Emotion moves
│   │   ├── speech_sway.py      # Speech-driven head micro-movements (338 lines)
│   │   └── reachy_motion.py    # Reachy motion API
│   │
│   ├── vision/                 # Vision processing modules
│   │   ├── __init__.py         # Module exports (30 lines)
│   │   ├── frame_processor.py  # Adaptive frame rate management (227 lines)
│   │   ├── face_tracking_interpolator.py  # Face lost interpolation (253 lines)
│   │   ├── gesture_smoother.py  # Gesture history tracking (80 lines)
│   │   ├── gesture_detector.py  # HaGRID gesture detection (285 lines)
│   │   ├── head_tracker.py     # YOLO face detector (367 lines)
│   │   └── camera_server.py     # MJPEG camera stream server + face tracking (1009 lines)
│   │
│   ├── audio/                  # Audio runtime modules
│   │   ├── __init__.py         # Module exports (21 lines)
│   │   ├── microphone.py       # Hardware audio helper / legacy tuning code (219 lines)
│   │   ├── doa_tracker.py      # Direction of Arrival tracking (206 lines)
│   │   └── audio_player.py     # TTS + Sendspin playback (679 lines)
│   │
│   ├── entities/               # Home Assistant entity modules
│   │   ├── __init__.py         # Module exports (38 lines)
│   │   ├── entity.py           # ESPHome base entity (402 lines)
│   │   ├── entity_factory.py   # Entity factory pattern (440 lines)
│   │   ├── entity_keys.py      # Entity key constants (155 lines)
│   │   ├── entity_extensions.py  # Extended entity types (258 lines)
│   │   ├── entity_registry.py  # ESPHome entity registry (844 lines)
│   │   ├── event_emotion_mapper.py  # HA event to emotion mapping (351 lines)
│   │   └── emotion_detector.py # Disabled runtime path for text emotion detection
│   │
│   ├── animations/             # Animation definitions
│   │   └── conversation_animations.json  # Unified animations / gestures / HA events / keyword resources
│   │
│   └── wakewords/              # Wake word models
│       ├── okay_nabu.json/.tflite
│       ├── hey_jarvis.json/.tflite (openWakeWord)
│       ├── alexa.json/.tflite
│       ├── hey_luna.json/.tflite
│       └── stop.json/.tflite   # Stop word detection
│
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
    "reachy-mini[gstreamer]>=1.4.1",
    "reachy-mini-motor-controller>=1.5.5",
    "soundfile>=0.13.0",
    "numpy>=2.0.0,<=2.2.5",
    "opencv-python>=4.12.0.88",
    "pymicro-wakeword>=2.0.0,<3.0.0",
    "pyopen-wakeword>=1.0.0,<2.0.0",
    "aioesphomeapi>=43.10.1",
    "zeroconf<1",
    "scipy>=1.14.0",
    "ultralytics",
    "supervision",
    "aiosendspin>=2.0.1",
    "onnxruntime>=1.18.0",
    "torch==2.5.1",
    "torchvision==0.20.1",
    "pillow<12.0",
    "pydantic<=2.12.5",
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
| `Switch` | `sleep_control` | `request_sleep_state()` | off=awake/on=sleeping | Unified sleep/wake control |
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

#### Current Runtime Control and Sensor Entities

| Phase | ESPHome Entity Type | Name | Description |
|------|---------------------|------|-------------|
| 1 | `Switch` | `mute` | Suspend/resume the voice pipeline |
| 1 | `Switch` | `camera_disabled` | Suspend/resume camera processing |
| 1 | `Switch` | `idle_behavior_enabled` | Unified idle motion / antenna / micro-actions toggle |
| 1 | `Switch` | `sendspin_enabled` | Enable/disable Sendspin playback integration |
| 1 | `Switch` | `face_tracking_enabled` | Enable/disable face tracking models |
| 1 | `Switch` | `gesture_detection_enabled` | Enable/disable gesture detection models |
| 1 | `Number` | `face_confidence_threshold` | Face tracking confidence threshold (0-1) |
| 2 | `Switch` | `sleep_control` | Unified sleep/wake control |
| 8 | `Select` | `emotion` | Manual emotion trigger |
| 10 | `Camera` | `camera` | ESPHome camera entity / live preview |
| 21 | `Switch` | `continuous_conversation` | Multi-turn conversation mode |
| 22 | `Text Sensor` | `gesture_detected` | Current detected gesture |
| 22 | `Sensor` | `gesture_confidence` | Current gesture confidence |
| 23 | `Binary Sensor` | `face_detected` | Face currently visible |

> **Note**: Head position (x/y/z) and angles (roll/pitch/yaw), body yaw, antenna angles are all **controllable** entities,
> using `Number` type for bidirectional control. Call `goto_target()` when setting new values, call `get_current_head_pose()` etc. when reading current values.

### Implementation Priority

1. **Phase 1 - Basic Status and Volume** (High Priority) ✅ **Completed**
   - [x] `daemon_state` - Daemon status sensor
   - [x] `backend_ready` - Backend ready status
   - [x] `error_message` - Error message
   - [x] `speaker_volume` - Speaker volume control

2. **Phase 2 - Sleep and Runtime State** (High Priority) ✅ **Completed**
   - [x] `sleep_control` - Unified sleep/wake switch
   - [x] `sleep_mode` - Awake/sleeping state sensor
   - [x] `services_suspended` - Service suspension state sensor

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

9. **Phase 10 - Camera Integration** ✅ **Completed**
    - [x] `camera` - ESPHome Camera entity (live preview)

10. **Phase 11 - LED Control** ❌ **Disabled (LEDs hidden inside robot)**
    - [ ] `led_brightness` - LED brightness (0-100%) - Commented out
    - [ ] `led_effect` - LED effect (off/solid/breathing/rainbow/doa) - Commented out
    - [ ] `led_color_r/g/b` - LED RGB color (0-255) - Commented out

11. **Phase 13 - Sendspin Audio Playback Support** ✅ **Completed**
    - [x] `sendspin_enabled` - Sendspin switch (Switch)
    - [x] AudioPlayer integrates aiosendspin library
    - [x] TTS audio sent to both local speaker and Sendspin server

12. **Phase 21 - Continuous Conversation** ✅ **Completed**
    - [x] `continuous_conversation` - Conversation continuation switch

13. **Phase 22 - Gesture Detection** ✅ **Completed (v1.0.0 behavior)**
    - [x] `gesture_detected` - Detected gesture name (Text Sensor)
    - [x] `gesture_confidence` - Gesture detection confidence % (Sensor)
    - [x] HaGRID ONNX models: hand_detector.onnx + crops_classifier.onnx
    - [x] Real-time state push to Home Assistant
    - [x] GestureSmoother fast confirm + grace clear behavior
    - [x] Runtime toggle supported (default OFF, model unload on disable)
    - [x] Batch detection: returns all detected hands (not just highest confidence)
    - [x] Minimum processing cadence preserved for responsiveness
    - [x] No conflicts with face tracking (shared frame, independent processing)
    - [x] SDK integration: MediaBackend detection, proper resource cleanup on shutdown
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

14. **Phase 23 - Face Detection** ✅ **Completed**
    - [x] `face_detected` - Face visibility sensor

15. **Phase 24 - System Diagnostics** ✅ **Completed**
    - [x] `sys_cpu_percent` - CPU usage percentage (Sensor, diagnostic)
    - [x] `sys_cpu_temperature` - CPU temperature in Celsius (Sensor, diagnostic)
    - [x] `sys_memory_percent` - Memory usage percentage (Sensor, diagnostic)
    - [x] `sys_memory_used` - Used memory in GB (Sensor, diagnostic)
    - [x] `sys_disk_percent` - Disk usage percentage (Sensor, diagnostic)
    - [x] `sys_disk_free` - Free disk space in GB (Sensor, diagnostic)
    - [x] `sys_uptime` - System uptime in hours (Sensor, diagnostic)
    - [x] `sys_process_cpu` - This process CPU usage (Sensor, diagnostic)
    - [x] `sys_process_memory` - This process memory in MB (Sensor, diagnostic)

---

## 🎉 Current Runtime Entity Coverage

**Total Completed: See runtime registry (count evolves with releases)**
- Phase 1: 10 entities (status, zero-config runtime switches, volume)
- Phase 2: 3 entities (sleep and runtime state)
- Phase 3: 9 entities (Pose control)
- Phase 4: 3 entities (Gaze control)
- Phase 5: 3 entities (DOA sensors and tracking switch)
- Phase 6: 7 entities (Diagnostic information)
- Phase 7: 7 entities (IMU sensors)
- Phase 8: 1 entity (Emotion control)
- Phase 10: 1 entity (Camera)
- Phase 11: 0 entities (LED control - Disabled)
- Phase 13: 1 entity (Sendspin toggle)
- Phase 21: 1 entity (Continuous conversation)
- Phase 22: 2 entities (Gesture detection)
- Phase 23: 1 entity (Face detection)
- Phase 24: 9 entities (System diagnostics)


---

## 🚀 Voice Assistant Enhancement Features Implementation Status

### Phase 14 - Emotion and Motion Feedback ✅

**Current Status**: Manual emotion playback and non-blocking motion feedback are implemented. Automatic keyword-based emotion triggering is currently disabled in the runtime.

**Implemented Features**:
- ✅ Phase 8 Emotion Selector entity (`emotion`)
- ✅ `_play_emotion()` queues emotion moves through `MovementManager`
- ✅ Wake/listen/think/speak/idle motion transitions are non-blocking
- ✅ Timer-finished motion feedback is implemented
- ✅ Gesture detection publishes recognized gesture label and confidence to Home Assistant entities
- ✅ Voice phases and HA state reactions share one built-in behavior dispatcher

**Current Behavior**:

| Voice Assistant Event | Actual Action | Implementation Status |
|----------------------|---------------|----------------------|
| Wake word detected | Turn toward sound source + listening pose | ✅ Implemented |
| Listening | Attentive listening state | ✅ Implemented |
| Thinking | Thinking state animation | ✅ Implemented |
| Speaking | Speech-reactive motion | ✅ Implemented |
| Timer completed | Alert shake motion | ✅ Implemented |
| Manual emotion trigger | Play via ESPHome `emotion` entity | ✅ Implemented |

**Deliberately Not Active In Runtime**:
- Automatic emotion keyword detection from assistant text
- Blocking full-action choreography during conversation
- Dance/personalization layers that require user configuration

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
| DOA turn-to-sound | Turn toward speaker at wakeup | `protocol/satellite.py:_turn_to_sound_source()` | ✅ Implemented |
| YOLO face detection | Uses `AdamCodd/YOLOv11n-face-detection` model | `vision/head_tracker.py` | ✅ Implemented |
| Adaptive frame rate tracking | 15fps during conversation, 2fps when idle without face | `camera_server.py` | ✅ Implemented |
| look_at_image() | Calculate target pose from face position | `camera_server.py` | ✅ Implemented |
| Smooth return to neutral | Smooth return within 1 second after face lost | `camera_server.py` | ✅ Implemented |
| face_tracking_offsets | As secondary pose overlay to motion control | `movement_manager.py` | ✅ Implemented |
| Body follows head rotation | Body yaw syncs with head yaw extracted from final pose matrix | `motion/movement_manager.py:_compose_final_pose()` | ✅ Implemented (v0.8.3) |
| DOA entities | `doa_angle` and `speech_detected` exposed to Home Assistant | `entity_registry.py` | ✅ Implemented |
| face_detected entity | Binary sensor for face detection state | `entity_registry.py` | ✅ Implemented |
| Model download retry | 3 retries, 5 second interval | `head_tracker.py` | ✅ Implemented |
| Conversation mode integration | Auto-switch tracking frequency on voice assistant state change | `satellite.py` | ✅ Implemented |

**Resource Optimization (v0.5.1, updated v0.6.2)**:
- During conversation (listening/thinking/speaking): High-frequency tracking 15fps
- Idle with face detected: High-frequency tracking 15fps
- Idle without face for 5s: Low-power mode 2fps
- Idle without face for 30s: Ultra-low power mode 0.5fps (every 2 seconds)
- Gesture detection is switch-controlled and can run independently of face tracking
- Immediately restore high-frequency tracking when face detected

**Code Locations**:
- `protocol/satellite.py:_turn_to_sound_source()` - DOA turn-to-sound at wakeup
- `vision/head_tracker.py` - YOLO face detector (`HeadTracker` class)
- `vision/camera_server.py:_capture_frames()` - Adaptive frame rate face tracking
- `vision/camera_server.py:set_conversation_mode()` - Conversation mode switch API
- `protocol/satellite.py:_set_conversation_mode()` - Voice assistant state integration
- `motion/movement_manager.py:set_face_tracking_offsets()` - Face tracking offset API
- `motion/movement_manager.py:_compose_final_pose()` - Body yaw follows head yaw (v0.8.3)

**Technical Details**:
```python
# vision/camera_server.py - Adaptive frame rate face tracking
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

# protocol/satellite.py - Voice assistant state integration
def _reachy_on_listening(self):
    self._set_conversation_mode(True)  # Start conversation, high-frequency tracking

def _reachy_on_idle(self):
    self._set_conversation_mode(False)  # End conversation, adaptive tracking

# motion/movement_manager.py - Body follows head rotation (v0.8.3)
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
- ✅ 50Hz unified control loop (`motion/movement_manager.py`) - Current stable frequency
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
- `motion/animation_player.py` - AnimationPlayer class
- `animations/conversation_animations.json` - Animation definitions
- `motion/movement_manager.py` - 50Hz control loop with animation integration

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
- ✅ v1.0.0 idle refinement: idle antenna sway disabled while conversation-state antenna behaviors are retained
- ✅ v1.0.0 hardware refinement: antenna torque disabled in `IDLE` to reduce idle chatter/noise

**Code Locations**:
- `motion/animation_player.py` - AnimationPlayer with antenna offset calculation
- `animations/conversation_animations.json` - Antenna amplitude and pattern definitions
- `motion/movement_manager.py` - Antenna offset composition in final pose

### Phase 18 - Visual Gaze Interaction (Single-face only) ✅

**Goal**: Use camera to detect faces for eye contact.

**SDK Support**:
- `look_at_image(u, v)` - Look at point in image
- `look_at_world(x, y, z)` - Look at world coordinate point
- `media.get_frame()` - Get camera frame (✅ Already implemented in `vision/camera_server.py:146`)

**Current Status**:

| Feature | Description | Status |
|---------|-------------|--------|
| Face detection | YOLO-based face detection (`AdamCodd/YOLOv11n-face-detection`) | ✅ Implemented |
| Eye tracking | Robot tracks detected face during conversation/active mode | ✅ Implemented |
| Idle scanning | Random look-around in idle cycles (switch-controlled) | ✅ Implemented |

> Scope note: Current implementation is intentionally single-face tracking for stability and device performance.

### Phase 19 - Gravity Compensation Interactive Mode (Historical / Not Current Target)

This was an exploration direction for manual teaching workflows.

**Current Runtime Position**:
- The zero-config runtime does not depend on a teaching flow
- No user-facing teaching interaction is exposed as a core feature
- If gravity-compensation support is revisited, it should remain optional and not become a required setup path

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

### Phase 21 - Home Assistant Orchestration Scope

The current runtime already exposes the main zero-config controls needed by Home Assistant:

- `sleep_control`
- `idle_behavior_enabled`
- `continuous_conversation`
- `emotion`
- gesture / face / diagnostic sensors

More elaborate scene orchestration remains intentionally outside the core runtime scope unless it can be delivered without introducing user configuration burden.


---

## 📊 Feature Implementation Summary

### ✅ Completed Features

#### Core Voice Assistant (Phase 1-12)
- **ESPHome entities** - Core phases implemented (Phase 11 LED intentionally disabled); exact count evolves by release
- **Basic voice interaction** - Wake word detection (microWakeWord/openWakeWord), STT/TTS integration
- **Motion feedback** - Nod, shake, gaze and other basic actions
- **Audio path** - local wake word / stop word detection plus HA-managed STT/TTS
- **Camera stream** - MJPEG live preview with ESPHome Camera entity

#### Extended Features (Phase 13-22)
- **Phase 13** ✅ - Sendspin multi-room audio support
- **Phase 14** ✅ - Manual emotion playback + non-blocking motion feedback
- **Phase 15** ✅ - Face tracking with body following (DOA + YOLO + body_yaw sync)
- **Phase 16** ✅ - JSON-driven animation system (50Hz control loop)
- **Phase 17** ✅ - Antenna sync animation during speech
- **Phase 22** ✅ - Gesture detection (HaGRID ONNX, 18 gestures)

### 🟡 Partially Implemented Features

- **Phase 20** - IMU sensor entities are exposed; higher-level trigger logic is intentionally minimal

### ❌ Not Implemented Features

- Zero-config scene orchestration beyond the provided runtime switches and blueprint defaults

---

## Feature Priority Summary (Updated v1.0.0)

### Completed ✅
- ✅ **Phase 1-12**: Core ESPHome entities and voice assistant
- ✅ **Phase 13**: Sendspin audio playback
- ✅ **Phase 14**: Emotion playback and motion feedback
- ✅ **Phase 15**: Face tracking with body following
- ✅ **Phase 16**: JSON-driven animation system
- ✅ **Phase 17**: Antenna sync animation + v1.0.0 idle antenna behavior refinements
- ✅ **Phase 21**: Continuous conversation switch
- ✅ **Phase 22**: Gesture detection
- ✅ **Phase 23**: Face detection sensor
- ✅ **Phase 24**: System diagnostics (psutil-based)

### Partial 🟡
- 🟡 **Phase 20**: Environment awareness (IMU entities done, triggers pending)

### Not Implemented ❌
- ❌ Zero-config scene orchestration layer beyond current runtime behavior

---

## 📈 Completion Statistics

| Phase | Status | Completion | Notes |
|-------|--------|------------|-------|
| Phase 1-12 | ✅ Complete | 100% | Core ESPHome entities implemented (Phase 11 LED intentionally disabled) |
| Phase 13 | ✅ Complete | 100% | Sendspin audio playback support |
| Phase 14 | ✅ Complete | 100% | Manual emotion playback and non-blocking motion feedback |
| Phase 15 | ✅ Complete | 100% | Face tracking with DOA, YOLO detection, body follows head |
| Phase 16 | ✅ Complete | 100% | JSON-driven animation system (50Hz control loop) |
| Phase 17 | ✅ Complete | 100% | Antenna sync animation during speech |
| Phase 18 | ✅ Complete | 100% | Single-face visual gaze interaction with idle scanning |
| Phase 19 | Not a current runtime target | - | Historical planning item, not part of the zero-config runtime model |
| Phase 20 | 🟡 Partial | 30% | IMU sensors exposed, missing trigger logic |
| Phase 21 | ✅ Complete | 100% | Continuous conversation switch implemented |
| Phase 22 | ✅ Complete | 100% | Gesture detection with HaGRID ONNX models |
| Phase 23 | ✅ Complete | 100% | Face detection sensor exposed |
| Phase 24 | ✅ Complete | 100% | System diagnostics with psutil (9 sensors) |
| **v0.9.5** | ✅ Complete | 100% | Modular architecture refactoring |
| **v1.0.0** | ✅ Complete | 100% | Runtime toggles/persistence (Sendspin, face, gesture, confidence) + idle and gesture stability updates |

**Overall Completion**: current zero-config runtime path is functionally complete; remaining gaps are optional orchestration ideas rather than missing core runtime features.


---

## 🔧 Daemon Crash Fix (2025-01-05)

### Problem Description
During long-term operation, `reachy_mini daemon` would crash, causing robot to become unresponsive.

### Root Cause
1. **50Hz control loop** - Current stable frequency for motion control
2. **Frequent state queries** - Every entity state read calls `get_status()`, `get_current_head_pose()` etc.
3. **Missing change detection** - Even when pose hasn't changed, continues sending same commands
4. **Zenoh message queue blocking** - Accumulated 150+ messages per second, daemon cannot process in time

### Fix Solution

#### 1. Control loop frequency (motion/movement_manager.py)
```python
# Evolution: 100Hz -> 20Hz -> 10Hz -> 50Hz (current)
# Current stable frequency for production use
CONTROL_LOOP_FREQUENCY_HZ = 50  # Current stable frequency
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

> **Update (2026-01-30)**: Current implementation uses 50Hz control loop for stability and performance. The control loop frequency aligns with daemon backend processing capacity. The pose change threshold (0.005) and state cache TTL (2s) optimizations remain in place to reduce unnecessary Zenoh messages.

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

#### 1. Control loop frequency history (motion/movement_manager.py)
```python
# Evolution: 100Hz -> 20Hz -> 10Hz -> 50Hz (current)
# Current stable frequency for production use
CONTROL_LOOP_FREQUENCY_HZ = 50  # Current (2026-01-30)
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

> **Note**: Current implementation uses 50Hz control loop as of 2026-01-30. The table below shows historical evolution.

| Metric | Before (20Hz) | After (10Hz) | Current (50Hz) |
|--------|---------------|--------------|-----------------|
| Control loop frequency | 20 Hz | 10 Hz | 50 Hz (current) |
| Max Zenoh messages | 60 msg/s | 30 msg/s | ~50 msg/s (optimized) |
| Actual messages (with change detection) | ~40 msg/s | ~15 msg/s | ~30 msg/s |
| Face tracking frequency | 15 Hz | 10 Hz | Adaptive (2-15 Hz) |
| State cache TTL | 1 second | 2 seconds | 2 seconds |
| Expected stability | Crash within hours | Stable operation | Stable (daemon updated) |

### Key Finding

Current implementation uses 50Hz control loop for stability and performance. The control loop frequency aligns with daemon backend processing capacity.

### Related Files
- `motion/movement_manager.py` - Control loop frequency and pose threshold
- `vision/camera_server.py` - Face tracking frequency
- `reachy_controller.py` - State cache TTL


---

## 🔧 Microphone Sensitivity Optimization (2026-01-07)

> Historical background only. These notes describe earlier low-level microphone tuning experiments and should not be read as current Home Assistant entity capabilities.

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

**Fix**: Added `pause_sendspin()` and `resume_sendspin()` methods to `audio/audio_player.py`

### Issue 3: Sendspin Sample Rate Optimization

**Fix**: Prioritize 16kHz in Sendspin supported formats (hardware limitation)

---

## 🔧 v0.5.15 Updates (2026-01-11)

### Feature 1: Audio Settings Persistence

Historical note: older audio processing preferences were once persisted here. The current app no longer exposes AGC or noise suppression entities.

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

ESPHome protocol communicates with Home Assistant via protobuf messages. The runtime primarily uses switch/number/select/sensor/binary_sensor/text_sensor/camera entities; button-only wake/sleep flows are historical and no longer the main control model.

```python
from aioesphomeapi.api_pb2 import (
    # Number entity (volume/angle/confidence control)
    ListEntitiesNumberResponse,
    NumberStateResponse,
    NumberCommandRequest,

    # Select entity (emotion)
    ListEntitiesSelectResponse,
    SelectStateResponse,
    SelectCommandRequest,

    # Switch entity (sleep/runtime toggles)
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

---

## 🔧 Code Refactoring & Improvement Plan (v0.9.5)

> Comprehensive improvement plan based on code analysis
> Target Platform: Raspberry Pi CM4 (4GB RAM, 4-core CPU)

### Code Size Statistics (Updated 2026-01-19)

| File | Original | Current | Status |
|------|----------|---------|--------|
| `movement_manager.py` | 1205 | 1260 | ⚠️ Modularized but still large |
| `voice_assistant.py` | 1097 | 1270 | ✅ Enhanced with new features |
| `satellite.py` | 1003 | 1022 | ✅ Optimized (-2%) |
| `camera_server.py` | 1070 | 1009 | ✅ Optimized (-6%) |
| `reachy_controller.py` | 878 | 961 | ✅ Enhanced |
| `entity_registry.py` | 1129 | 844 | ✅ Optimized (-25%) |
| `audio_player.py` | 599 | 679 | ✅ Acceptable |
| `core/service_base.py` | - | 552 | 🆕 New module |
| `entities/entity_factory.py` | - | 440 | 🆕 New module |

> **Optimization Notes**:
> - `entity_registry.py`: Factory pattern refactoring reduced 285 lines
> - `camera_server.py`: Using `FaceTrackingInterpolator` module reduced 61 lines
> - `protocol/satellite.py`: Runtime paths are now centered on voice state handling and HA event reactions
> - New modular architecture with 6 sub-packages: `core/`, `motion/`, `vision/`, `audio/`, `entities/`, `protocol/`

### New Module List (Updated 2026-01-19)

| Directory | Module | Lines | Description |
|-----------|--------|-------|-------------|
| `core/` | `config.py` | 454 | Centralized nested configuration |
| `core/` | `daemon_monitor.py` | 377 | Daemon state monitoring + Sleep detection |
| `core/` | `service_base.py` | 552 | SleepAwareService + RobustOperationMixin |
| `core/` | `sleep_manager.py` | 278 | Sleep/Wake coordination |
| `core/` | `health_monitor.py` | 305 | Service health checking |
| `core/` | `memory_monitor.py` | 282 | Memory usage monitoring |
| `core/` | `robot_state_monitor.py` | 300 | Robot connection state monitoring |
| `core/` | `system_diagnostics.py` | 250 | System diagnostics |
| `core/` | `exceptions.py` | 68 | Custom exception classes |
| `core/` | `util.py` | 28 | Utility functions |
| `motion/` | `antenna.py` | - | Antenna freeze/unfreeze control |
| `motion/` | `pose_composer.py` | - | Pose composition utilities |
| `motion/` | `gesture_actions.py` | - | Gesture to action mapping |
| `motion/` | `state_machine.py` | - | State machine definitions |
| `motion/` | `smoothing.py` | - | Smoothing/transition algorithms |
| `motion/` | `animation_player.py` | - | Animation player |
| `motion/` | `emotion_moves.py` | - | Emotion moves |
| `motion/` | `speech_sway.py` | 338 | Speech-driven head micro-movements |
| `motion/` | `reachy_motion.py` | - | Reachy motion API |
| `vision/` | `frame_processor.py` | 227 | Adaptive frame rate management |
| `vision/` | `face_tracking_interpolator.py` | 253 | Face lost interpolation |
| `vision/` | `gesture_smoother.py` | 80 | Gesture history tracking |
| `vision/` | `gesture_detector.py` | 285 | HaGRID gesture detection |
| `vision/` | `head_tracker.py` | 367 | YOLO face detector |
| `vision/` | `camera_server.py` | 1009 | MJPEG camera stream server |
| `audio/` | `doa_tracker.py` | 206 | Direction of Arrival tracking |
| `audio/` | `microphone.py` | 219 | Hardware audio helper / legacy tuning code |
| `audio/` | `audio_player.py` | 679 | TTS + Sendspin playback |
| `entities/` | `entity.py` | 402 | ESPHome base entity |
| `entities/` | `entity_factory.py` | 440 | Entity factory pattern |
| `entities/` | `entity_keys.py` | 155 | Entity key constants |
| `entities/` | `entity_extensions.py` | 258 | Extended entity types |
| `entities/` | `event_emotion_mapper.py` | 351 | HA event to emotion mapping |
| `protocol/` | `satellite.py` | 1022 | ESPHome protocol handler |
| `protocol/` | `api_server.py` | 172 | HTTP API server |
| `protocol/` | `zeroconf.py` | - | mDNS discovery |

### Improvement Plan Status

#### Phase 1: Sleep State Management ✅ Complete

- [x] Create `core/daemon_monitor.py` - DaemonStateMonitor
- [x] Create `core/service_base.py` - SleepAwareService interface
- [x] Create `core/sleep_manager.py` - SleepManager
- [x] All services implement `suspend()`/`resume()` methods
- [x] Add Sleep state sensor to HA
- [ ] Test complete Sleep/Wake cycle

#### Phase 2: Code Modularization ✅ Complete

- [x] Create new directory structure (`core/`, `motion/`, `audio/`, `vision/`, `entities/`)
- [x] Extract from `movement_manager.py` → `motion/antenna.py`, `motion/pose_composer.py`
- [x] Extract from `camera_server.py` → `vision/frame_processor.py`, `vision/face_tracking_interpolator.py`
- [x] Extract from `entity_registry.py` → `entities/entity_factory.py`, `entities/entity_keys.py`
- [x] Create `core/config.py` for centralized configuration
- [x] Ensure no circular dependencies

#### Phase 3: Stability & Performance ✅ Complete

- [x] Create `core/exceptions.py` - Custom exception classes
- [x] Implement `RobustOperationMixin` - Unified error handling
- [x] `CameraServer` implements Context Manager pattern
- [x] Improve `CameraServer` resource cleanup
- [x] Fix MJPEG client tracking (proper register/unregister)
- [x] Add `core/health_monitor.py` - Service health checking
- [x] Add `core/memory_monitor.py` - Memory usage monitoring
- [ ] Long-running stability test (24h+)

#### Phase 4: Feature Enhancements ✅ Complete

- [x] Create `motion/gesture_actions.py` - GestureActionMapper
- [x] Fold gesture behavior config into `animations/conversation_animations.json`
- [x] Create `audio/doa_tracker.py` - DOATracker
- [x] Implement sound source tracking with motion control integration
- [x] Create `entities/event_emotion_mapper.py` - EventEmotionMapper
- [x] Fold HA event behavior config into `animations/conversation_animations.json`
- [x] Add DOA tracking toggle HA entity

### SDK Compatibility Verification ✅ Passed

| API Call | Status | Notes |
|----------|--------|-------|
| `set_target(head, antennas, body_yaw)` | ✅ | Correct usage |
| `goto_target()` | ✅ | Correct usage |
| `look_at_image(u: int, v: int)` | ✅ | Fixed float→int |
| `create_head_pose(degrees=False)` | ✅ | Using radians |
| `compose_world_offset()` | ✅ | SDK function correctly called |
| `linear_pose_interpolation()` | ✅ | Has fallback implementation |
| Body yaw range | ✅ | Clamped to ±160° |

---

## 🔧 v0.9.5 Updates (2026-01-19)

### Major Changes: Modular Architecture Refactoring

The codebase has been restructured into a modular architecture with 5 sub-packages:

| Package | Purpose | Key Modules |
|---------|---------|-------------|
| `core/` | Core infrastructure | `config.py`, `service_base.py`, `sleep_manager.py`, `health_monitor.py` |
| `motion/` | Motion control | `antenna.py`, `pose_composer.py`, `gesture_actions.py`, `smoothing.py` |
| `vision/` | Vision processing | `frame_processor.py`, `face_tracking_interpolator.py` |
| `audio/` | Audio processing | `microphone.py`, `doa_tracker.py` |
| `entities/` | HA entity management | `entity_factory.py`, `entity_keys.py`, `event_emotion_mapper.py` |

### New Features

1. **Direct Sleep/Wake Callbacks**
   - HA sleep/wake buttons directly call `suspend()`/`resume()` on services
   - More reliable than polling-based approach

2. **Synchronous Camera Resume**
   - `camera_server.resume_from_suspend()` is now synchronous
   - Ensures camera is ready before voice assistant starts listening

### Audio Optimizations

| Parameter | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Audio chunk size | 1024 samples | 256 samples | 64ms → 16ms latency |
| Audio loop delay | 10ms | 1ms | Faster VAD response |
| Stereo→Mono | Mean of channels | First channel | Cleaner signal |

### Code Quality Improvements

- Removed all legacy/compatibility code
- Centralized configuration in nested dataclasses
- NaN/Inf cleaning in audio pipeline
- Rotation clamping in face tracking to prevent IK collisions
