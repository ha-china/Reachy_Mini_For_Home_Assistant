# Reachy Mini for Home Assistant - Project Plan

## Project Overview

Integrate Home Assistant voice assistant functionality into Reachy Mini Wi-Fi robot, communicating with Home Assistant via ESPHome protocol.

Current package:
- `reachy_mini_home_assistant`

Current version:
- `1.0.7`

## Local Reference Directories (DO NOT modify any files in reference directories)

1. [linux-voice-assistant](reference/linux-voice-assistant) - Linux-based Home Assistant voice assistant app for reference
2. [Reachy Mini SDK](reference/reachy_mini) - Reachy Mini SDK local directory for reference
3. [reachy_mini_conversation_app](reference/reachy_mini_conversation_app) - Reachy Mini conversation app for reference
4. [reachy-mini-desktop-app](reference/reachy-mini-desktop-app) - Reachy Mini desktop app for reference
5. [sendspin](reference/sendspin-cli/) - Sendspin client for reference
6. [aiosendspin](reference/aiosendspin/) - Sendspin protocol client library reference
7. [dynamic_gestures](reference/dynamic_gestures/) - Dynamic gesture reference
8. [SimpleDances](reference/SimpleDances/) - Local reference snapshot

## Core Design Principles

1. **Zero Configuration** - Users only need to install the app, no manual configuration required
2. **Native Hardware** - Use robot's built-in microphone and speaker
3. **Home Assistant Centralized Management** - STT, TTS, and intent configuration stay on the Home Assistant side
4. **Motion Feedback** - Provide head movement and antenna animation feedback during voice interaction
5. **Project Constraints** - Strictly follow Reachy Mini SDK architecture design and current SDK constraints
6. **Code Quality** - Follow Python development standards with consistent code style, clear structure, and maintainability
7. **Feature Priority** - Voice conversation with Home Assistant is highest priority; other features are auxiliary and must not affect voice conversation functionality or response speed
8. **No LED Functions** - LEDs are hidden inside the robot; all LED control is ignored
9. **Preserve Functionality** - Any code modifications should optimize while preserving completed features; do not remove features to solve problems
10. **No App-Managed Sleep/Wake** - The app no longer manages robot sleep/wake transitions; current SDK behavior is treated as source of truth

## Technical Architecture

### Current Runtime Architecture (v1.0.7)

The current system is built around one main runtime service with motion, vision, audio, and Home Assistant entity subsystems.

```text
ReachyMiniHaVoice (main.py)
  -> VoiceAssistantService (voice_assistant.py)
     -> VoiceSatelliteProtocol server (protocol/satellite.py)
     -> Reachy Mini motion runtime (motion/)
     -> Camera and vision runtime (vision/)
     -> Local speech player + optional Sendspin player (audio/)
     -> Home Assistant entities and state publishing (entities/)
```

### Runtime Entry And Service Ownership

Current startup path:

1. `ReachyMiniHaVoice` in `main.py` is the Reachy Mini app entry point
2. `run()` creates one `VoiceAssistantService`
3. `VoiceAssistantService.start()` initializes runtime directories, loads wake word assets, loads preferences, builds server state, starts SDK media, starts the motion runtime, starts the audio processing thread, starts the ESPHome server, and registers mDNS discovery
4. Sendspin discovery is started only if enabled in stored preferences
5. The camera runtime is not started unconditionally at boot; it is reconciled later based on Home Assistant connection state, camera enable state, and idle behavior state

This means the real root of the current runtime is `VoiceAssistantService`, not the protocol class and not the camera server.

### Core Runtime Objects

Current always-important runtime objects:

| Object | Defined in | Current role |
|---|---|---|
| `ReachyMiniHaVoice` | `main.py` | App wrapper used by Reachy Mini SDK |
| `VoiceAssistantService` | `voice_assistant.py` | Main runtime orchestrator |
| `ServerState` | `models.py` | Shared mutable runtime state passed into protocol and entity layers |
| `VoiceSatelliteProtocol` | `protocol/satellite.py` | One ESPHome voice assistant protocol connection handler |
| `MovementManager` | `motion/movement_manager.py` | Unified movement and pose composition loop |
| `MJPEGCameraServer` | `vision/camera_server.py` | Camera HTTP server plus face and gesture runtime |
| `LocalAudioPlayer` | `audio/local_audio_player.py` | Local speech, wakeup, and timer playback |
| `AudioPlayer` | `audio/audio_player.py` | Music-capable playback facade with optional Sendspin support |

### Audio Input Path

The current audio input architecture is centered in `VoiceAssistantService`.

Actual runtime path:

1. `VoiceAssistantService.start()` validates SDK media availability
2. The service starts SDK recording and playback through `reachy_mini.media`
3. `_process_audio` in `voice_assistant.py` runs on a dedicated thread
4. That thread reads microphone samples from the SDK media backend
5. The same thread performs local wake word and stop word inference
6. When a voice session is active, the protocol object is used to forward audio chunks to Home Assistant

Important current constraint:

- Audio capture, local wake detection, and protocol audio forwarding are tied together through `VoiceAssistantService`; they are not separate daemons or separately owned services

### Voice Protocol Path

The current Home Assistant voice path is centered in `VoiceSatelliteProtocol` and helper modules under `protocol/`.

Actual structure:

1. `VoiceAssistantService` creates an asyncio server using `VoiceSatelliteProtocol`
2. Each protocol instance receives the shared `ServerState`, optional camera server, and a back-reference to `VoiceAssistantService`
3. `protocol/message_dispatch.py` routes incoming protobuf messages
4. `protocol/session_flow.py` manages wakeup sequencing, wakeup sound completion, pending voice request flow, and delayed idle return helpers
5. `protocol/voice_pipeline.py` manages TTS playback, timer playback, ducking, unducking, and stop behavior
6. `protocol/motion_bridge.py` maps voice assistant phases to robot motion callbacks
7. `protocol/entity_bridge.py` connects protocol state with entity setup and camera callbacks

Current protocol state held inside `VoiceSatelliteProtocol` includes:

- whether audio streaming is active
- pending TTS URL
- timer playback state
- pending wakeup-triggered voice request
- continuous conversation state
- conversation ID and timeout tracking
- delayed return-to-idle timer
- per-connection Home Assistant entity state cache

### Motion Control Architecture

The current motion system is not just a set of direct SDK calls. It is a composed control runtime centered on `MovementManager`.

Actual structure:

1. `VoiceAssistantService` creates `ReachyMiniMotion`, which exposes `movement_manager`
2. `movement_manager.py` owns the long-running control loop thread
3. External requests are pushed into a command queue instead of directly mutating robot state from many threads
4. The loop composes final head pose, antenna pose, and body yaw before sending commands
5. Command polling and state transition handling are split into `command_runtime.py`
6. Control emission helpers are split into `control_runtime.py`
7. Idle behavior logic is split into `idle_runtime.py`
8. Smoothing and pose composition are split into `smoothing.py` and `pose_composer.py`

Current motion inputs that feed the final composed pose:

- explicit pose commands from Home Assistant entities
- robot state transitions such as listening, thinking, speaking, and idle
- emotion or action moves
- speech sway from playback
- face tracking offsets from the camera runtime
- idle behavior and idle random actions
- DOA-triggered turn-to-sound behavior

Current DOA integration:

- `MovementManager` owns a `DOATracker`
- wakeup turn-to-sound behavior is invoked from the protocol layer
- DOA is part of current runtime behavior, but it is not a separate architecture layer

### Vision And Camera Architecture

The current camera system is conditional and service-managed, not always-on.

Actual lifecycle:

1. `VoiceAssistantService` decides whether the camera runtime should exist
2. `_reconcile_camera_runtime()` starts or stops `MJPEGCameraServer` depending on:
   - app camera enable flag
   - Home Assistant connection state
   - stored idle behavior preference
3. `MJPEGCameraServer` owns the HTTP camera surface and capture thread
4. Runtime helper modules split camera responsibilities:
   - `camera_runtime.py` for lifecycle and model load/unload helpers
   - `camera_processing.py` for frame capture, AI processing, and stream helpers
   - `camera_http.py` for `/`, `/stream`, and `/snapshot` handlers
5. Face tracking and gesture detection are optional capabilities inside the same camera runtime

Current important behavior:

- camera runtime can be fully stopped when idle behavior is off
- the stream is viewer-aware to reduce MJPEG work when no client is connected
- `/snapshot` can encode on demand
- face and gesture models can be independently requested through runtime preferences

### Audio Output Architecture

The current playback design intentionally separates local speech playback from Sendspin-capable playback.

Actual split:

1. `LocalAudioPlayer` is stored in `ServerState.tts_player`
2. `AudioPlayer` is stored in `ServerState.music_player`
3. TTS, wakeup, and timer sounds go through the local player path
4. Sendspin discovery, connection, buffering, remote commands, and synchronized playback live in the music player path
5. `VoiceSatelliteProtocol` configures a speech sway callback on the TTS player so audio playback can drive head micro-movements

Current audio module split:

- `audio_player_playback.py` handles generic playback lifecycle
- `audio_player_local.py` handles local file and in-memory fallback playback
- `audio_player_stream_pcm.py` handles streamed PCM playback
- `audio_player_stream_decoded.py` handles decoded streamed audio playback
- `audio_player_sendspin.py` handles Sendspin integration
- `audio_player_shared.py` holds shared constants and helpers

### Entity And Control Architecture

The current entity architecture is built from setup helpers rather than one giant registry file.

Actual structure:

1. `VoiceSatelliteProtocol` creates the entity registry through `entity_bridge.py`
2. `initialize_entities()` wires entities only once per shared server state
3. `runtime_entity_setup.py` registers runtime control entities such as:
   - `speaker_volume`
   - `mute`
   - `camera_disabled`
   - `idle_behavior_enabled`
   - `sendspin_enabled`
   - `face_tracking_enabled`
   - `gesture_detection_enabled`
   - `face_confidence_threshold`
   - `emotion`
   - `continuous_conversation`
4. `sensor_entity_setup.py` registers state, observation, and diagnostic entities
5. `entity_registry.py` keeps references to live entity objects and pushes updates back to Home Assistant

Current important behavior:

- many switches are backed by persisted preferences
- vision-related switches call back into camera runtime state application
- `mute` directly suspends or resumes voice services through `VoiceAssistantService`
- `sendspin_enabled` directly toggles Sendspin discovery and connection through `VoiceAssistantService`

### Runtime Suspension Architecture

The current system has two suspension scopes, both owned by `VoiceAssistantService`.

Voice-only suspension:

- `_suspend_voice_services()` and `_resume_voice_services()`
- used for mute-like behavior
- stops or resumes media and protocol voice path while leaving camera and motion available

Non-ESPHome service suspension:

- `_suspend_non_esphome_services()` and `_resume_non_esphome_services()`
- can suspend camera, motion, audio players, satellite runtime, and media system together while keeping the outer ESPHome presence alive

This is the real current architecture for runtime pause behavior. It is not based on the removed app-managed sleep/wake design.

### Runtime State Flow

The current conversation flow is driven by wake detection plus protocol state.

```text
idle
  -> local wake word detected
  -> wakeup sound and optional turn-to-sound
  -> listening
  -> thinking
  -> speaking
  -> delayed return or direct return to idle
```

Current interruption paths:

- stop word during interruptible context
- timer ring interruption flow
- Home Assistant disconnection
- mute-driven voice suspension

### System Boundaries

The current system boundary is:

- Reachy Mini SDK owns robot media and hardware access
- this app owns wake logic, playback logic, motion feedback, optional camera AI, and Home Assistant entity behavior
- Home Assistant owns speech recognition, intent handling, and response generation

That is the current project architecture reflected by the codebase.

## Usage Flow

1. Install the app as a Reachy Mini app
2. Start the app on the robot
3. The app initializes SDK media, loads wake word assets, and starts the ESPHome server on port `6053`
4. Home Assistant discovers the robot automatically through mDNS, or it can be added manually as an ESPHome device
5. The user says a wake phrase such as `Okay Nabu`
6. The app streams audio to Home Assistant and waits for conversation events or TTS audio in return
7. Reachy Mini plays local speech audio, applies motion feedback, and returns to idle when the interaction finishes

Manual runtime controls are exposed through Home Assistant entities, including mute, idle behavior, continuous conversation, camera control, face tracking, gesture detection, and Sendspin enablement

## Current Runtime Defaults

- `sendspin_enabled`: off by default
- `face_tracking_enabled`: off by default
- `gesture_detection_enabled`: off by default
- `continuous_conversation`: user-controlled
- `idle_behavior_enabled`: user-controlled
- `face_confidence_threshold`: persistent user setting, default runtime threshold `0.5`

Behavior notes:
- When idle behavior is off, the camera server is stopped to reduce resource usage
- When face or gesture features are disabled, their models are unloaded
- Camera snapshots can be generated on demand when stream cache is empty
- TTS playback stays on the local player path even when Sendspin support is enabled
- Sendspin music playback is paused during voice assistant activity
- The app no longer owns sleep/wake state transitions; current SDK behavior is treated as authoritative
- Audio block size is `512` samples in the current runtime

## Voice And Motion Behavior

Conversation-related motion behavior:

- Wakeup can turn the head toward the current sound source using DOA information
- Listening, thinking, speaking, and idle phases each map to specific motion states
- Head, body yaw, antenna motion, breathing, and speech sway are combined through the motion stack
- Built-in emotion moves and Home Assistant-triggered behaviors run through a shared behavior layer

Idle behavior notes:

- Idle behavior is user-controlled and persisted through preferences
- When idle behavior is off, the robot stays in a parked low-resource state
- When idle behavior is on, the motion runtime may use breathing, idle rest poses, and other configured behavior resources

## Vision And Tracking Behavior

Camera and AI behavior:

- The MJPEG stream is viewer-aware to avoid unnecessary continuous encoding work
- `/snapshot` can encode on demand when no cached frame is available
- Face tracking and gesture detection can continue independently of active stream viewers when their runtimes are enabled
- Face tracking uses a detector plus smoothing/interpolation helpers
- Gesture detection uses ONNX models and a gesture smoother for stable result publishing

Current feature toggles:

- `camera_disabled`
- `face_tracking_enabled`
- `gesture_detection_enabled`
- `face_confidence_threshold`

## Current Architecture

Top-level package layout:

```text
reachy_mini_home_assistant/
  __main__.py
  main.py
  models.py
  reachy_controller.py
  voice_assistant.py
  animations/
  audio/
  core/
  entities/
  handlers/
  models/
  motion/
  protocol/
  sounds/
  static/
  vision/
  voice/
  wakewords/
```

Key modules:

- `main.py` - Reachy Mini app entry point
- `voice_assistant.py` - runtime orchestration, media startup, audio thread management
- `reachy_controller.py` - SDK-facing control wrapper
- `models.py` - shared state and preference models

Core infrastructure:

- `core/config.py` - centralized configuration
- `core/service_base.py` - suspend/resume-aware service helpers
- `core/system_diagnostics.py` - runtime diagnostics
- `core/exceptions.py` - custom exception definitions
- `core/util.py` - common helpers

Protocol layer:

- `protocol/satellite.py` - ESPHome protocol facade
- `protocol/api_server.py` - protocol HTTP surface
- `protocol/entity_bridge.py` - entity/protocol glue
- `protocol/message_dispatch.py` - ESPHome message dispatch
- `protocol/motion_bridge.py` - voice-to-motion transition helpers
- `protocol/session_flow.py` - conversation lifecycle helpers
- `protocol/voice_pipeline.py` - voice event, TTS, stop, ducking flow
- `protocol/wakeword_assets.py` - wake word asset loading helpers
- `protocol/zeroconf.py` - mDNS discovery

Motion layer:

- `motion/movement_manager.py` - unified motion control loop
- `motion/command_runtime.py` - command queue and state transitions
- `motion/control_runtime.py` - control loop helpers
- `motion/idle_runtime.py` - idle behavior handling
- `motion/pose_composer.py` - multi-source pose composition
- `motion/smoothing.py` - pose smoothing
- `motion/speech_sway.py` - speech-driven head micro-movements
- `motion/animation_player.py` - animation playback
- `motion/emotion_moves.py` - built-in emotion actions
- `motion/antenna.py` - antenna behavior control
- `motion/reachy_motion.py` - motion API wrapper
- `motion/state_machine.py` - motion state definitions

Vision layer:

- `vision/camera_server.py` - MJPEG camera server facade
- `vision/camera_runtime.py` - camera lifecycle helpers
- `vision/camera_processing.py` - frame capture and processing helpers
- `vision/camera_http.py` - stream and snapshot handlers
- `vision/head_tracker.py` - face detector
- `vision/face_tracking_interpolator.py` - smooth face tracking transitions
- `vision/gesture_detector.py` - gesture detection runtime
- `vision/gesture_smoother.py` - gesture result stabilization
- `vision/frame_processor.py` - adaptive frame pacing

Audio layer:

- `audio/audio_player.py` - music/sendspin playback facade
- `audio/local_audio_player.py` - local speech playback facade
- `audio/audio_player_playback.py` - playback lifecycle helpers
- `audio/audio_player_local.py` - local file and fallback playback helpers
- `audio/audio_player_stream_pcm.py` - streamed PCM playback
- `audio/audio_player_stream_decoded.py` - decoded stream playback
- `audio/audio_player_sendspin.py` - Sendspin integration
- `audio/audio_player_shared.py` - shared constants and helpers
- `audio/audio_player_wobble.py` - speech sway analysis helpers
- `audio/doa_tracker.py` - direction-of-arrival tracking

Entity layer:

- `entities/entity.py` - base ESPHome entity types
- `entities/entity_factory.py` - entity construction
- `entities/entity_registry.py` - runtime registry
- `entities/entity_extensions.py` - extended entity implementations
- `entities/entity_keys.py` - entity key constants
- `entities/runtime_entity_setup.py` - runtime and control entities
- `entities/sensor_entity_setup.py` - sensor and diagnostic entities
- `entities/event_emotion_mapper.py` - Home Assistant event to emotion mapping
- `entities/emotion_detector.py` - currently disabled text emotion path

## Detailed File List

Top-level repository structure:

```text
reachy_mini_ha_voice/
  CHANGELOG.md
  Project_Summary.md
  README.md
  changelog.json
  pyproject.toml
  docs/
  home_assistant_blueprints/
  reachy_mini_home_assistant/
  reference/
  scripts/
  tests/
```

Application package structure:

```text
reachy_mini_home_assistant/
  __init__.py
  __main__.py
  main.py
  models.py
  reachy_controller.py
  voice_assistant.py
  animations/
    animation_config.py
    conversation_animations.json
  audio/
    audio_player.py
    local_audio_player.py
    audio_player_playback.py
    audio_player_local.py
    audio_player_stream_pcm.py
    audio_player_stream_decoded.py
    audio_player_sendspin.py
    audio_player_shared.py
    audio_player_wobble.py
    doa_tracker.py
  core/
    config.py
    exceptions.py
    service_base.py
    system_diagnostics.py
    util.py
  entities/
    entity.py
    entity_extensions.py
    entity_factory.py
    entity_keys.py
    entity_registry.py
    event_emotion_mapper.py
    runtime_entity_setup.py
    sensor_entity_setup.py
    emotion_detector.py
  motion/
    animation_player.py
    antenna.py
    command_runtime.py
    control_runtime.py
    emotion_moves.py
    idle_runtime.py
    movement_manager.py
    pose_composer.py
    reachy_motion.py
    smoothing.py
    speech_sway.py
    state_machine.py
  protocol/
    api_server.py
    entity_bridge.py
    message_dispatch.py
    motion_bridge.py
    satellite.py
    session_flow.py
    voice_pipeline.py
    wakeword_assets.py
    zeroconf.py
  sounds/
  static/
  vision/
    camera_http.py
    camera_processing.py
    camera_runtime.py
    camera_server.py
    face_tracking_interpolator.py
    frame_processor.py
    gesture_detector.py
    gesture_smoother.py
    head_tracker.py
  wakewords/
```

## Implemented Feature Areas

Core voice assistant:
- ESPHome voice assistant server
- mDNS auto-discovery
- Local wake word detection
- Stop word detection
- Audio streaming to Home Assistant
- Local TTS playback
- Continuous conversation toggle

Reachy Mini integration:
- SDK microphone input
- SDK speaker output
- Head, body yaw, and antenna motion control
- Speech-phase motion feedback
- Built-in emotion and animation support

Vision and tracking:
- Home Assistant camera entity
- MJPEG stream server
- On-demand snapshots
- Face tracking
- Gesture detection with runtime enable/disable

Audio enhancements:
- Local speech playback path
- Optional Sendspin synchronized audio playback
- Ducking during conversation
- Shared sway behavior for speech and audio playback

Diagnostics and control:
- Runtime suspend/resume state
- System diagnostics entities
- Camera/face/gesture/sendspin switches
- Idle behavior switch

## Home Assistant Entity Coverage

The exact entity count evolves over time, but the current runtime exposes entities in these groups:

1. Voice assistant and media entities
2. Runtime switches and preferences
3. Head, body, and antenna pose control entities
4. Gaze target entities
5. DOA and speech-related sensors
6. Face tracking and gesture sensors
7. Camera entity
8. System diagnostic sensors
9. Emotion and behavior control entities

Representative control entities:

- `speaker_volume`
- `mute`
- `idle_behavior_enabled`
- `continuous_conversation`
- `sendspin_enabled`
- `camera_disabled`
- `face_tracking_enabled`
- `gesture_detection_enabled`
- `face_confidence_threshold`
- `head_x`, `head_y`, `head_z`
- `head_roll`, `head_pitch`, `head_yaw`
- `body_yaw`
- `antenna_left`, `antenna_right`
- `look_at_x`, `look_at_y`, `look_at_z`
- `emotion`

Representative sensor entities:

- `daemon_state`
- `backend_ready`
- `error_message`
- `doa_angle`
- `speech_detected`
- `services_suspended`
- `gesture_detected`
- `gesture_confidence`
- `face_detected`
- `sdk_version`
- `robot_name`
- `wlan_ip`
- system diagnostic entities such as CPU, memory, disk, uptime, and process metrics

## ESPHome Entity Planning And Current Mapping

Implemented core entities:

| Entity Type | Name | Purpose |
|---|---|---|
| Media Player | `media_player` | Audio playback control |
| Voice Assistant | `voice_assistant` | Voice assistant pipeline integration |

Implemented control entities:

| Entity Type | Name | Description |
|---|---|---|
| Number | `speaker_volume` | Speaker volume control |
| Switch | `mute` | Suspend or resume the voice pipeline |
| Switch | `idle_behavior_enabled` | Unified idle motion and idle behavior toggle |
| Switch | `camera_disabled` | Disable or enable camera runtime |
| Switch | `sendspin_enabled` | Enable or disable Sendspin playback integration |
| Switch | `face_tracking_enabled` | Enable or disable face tracking |
| Switch | `gesture_detection_enabled` | Enable or disable gesture detection |
| Number | `face_confidence_threshold` | Face tracking confidence threshold |
| Switch | `continuous_conversation` | Multi-turn conversation mode |
| Select | `emotion` | Manual emotion trigger |
| Number | `head_x`, `head_y`, `head_z` | Head position control |
| Number | `head_roll`, `head_pitch`, `head_yaw` | Head angle control |
| Number | `body_yaw` | Body yaw control |
| Number | `antenna_left`, `antenna_right` | Antenna angle control |
| Number | `look_at_x`, `look_at_y`, `look_at_z` | Gaze target control |

Implemented sensor entities:

| Entity Type | Name | Description |
|---|---|---|
| Text Sensor | `daemon_state` | Daemon state |
| Binary Sensor | `backend_ready` | Backend ready status |
| Text Sensor | `error_message` | Current error message |
| Sensor | `doa_angle` | Sound source direction angle |
| Binary Sensor | `speech_detected` | Speech detection status |
| Binary Sensor | `services_suspended` | Runtime suspension state |
| Text Sensor | `gesture_detected` | Current detected gesture |
| Sensor | `gesture_confidence` | Current gesture confidence |
| Binary Sensor | `face_detected` | Face visibility state |
| Text Sensor | `sdk_version` | SDK version |
| Text Sensor | `robot_name` | Robot name |
| Text Sensor | `wlan_ip` | Wireless IP address |
| Camera | `camera` | Live preview and snapshots |

System diagnostic entities include CPU, temperature, memory, disk, uptime, and process metrics.

Notes:

- Head position, head angles, body yaw, and antenna angles are all controllable runtime entities
- Gaze target entities are exposed as world-coordinate controls
- LED entities are intentionally not part of the current supported runtime surface

## Current Feature Status

Implemented core capabilities:

- ESPHome voice assistant integration
- Local wake word detection
- Stop word interruption
- TTS playback
- Continuous conversation toggle
- Reachy Mini motion feedback
- Camera streaming and snapshots
- Face tracking
- Gesture detection
- Sendspin integration
- Runtime diagnostics and Home Assistant controls

Important current constraints:

- STT, TTS voice generation, and intent handling stay on the Home Assistant side
- Optional features must not block or slow down core conversation behavior
- App-managed sleep/wake lifecycle has been removed because it no longer matches current SDK expectations
- LEDs are intentionally not part of the supported feature surface

## Implementation Priority Status

Phase-by-phase status carried forward in current terminology:

| Phase | Area | Status | Notes |
|---|---|---|---|
| 1 | Basic status and volume | Completed | Core runtime switches and volume are exposed |
| 2 | Runtime state | Completed | `services_suspended` remains; app-managed sleep entities were removed |
| 3 | Pose control | Completed | Head, body yaw, and antenna controls are exposed |
| 4 | Gaze control | Completed | `look_at_x/y/z` supported |
| 5 | DOA integration | Completed | Used for wakeup turn-to-sound and exposed through sensors |
| 6 | Diagnostic information | Completed | SDK and runtime diagnostics exposed |
| 7 | IMU sensors | Completed | Exposed where supported by the robot/runtime |
| 8 | Emotion control | Completed | Manual emotion trigger via select entity |
| 10 | Camera integration | Completed | Camera entity plus MJPEG runtime |
| 11 | LED control | Disabled by design | Not part of supported user-facing scope |
| 13 | Sendspin support | Completed | Optional synchronized playback path |
| 14 | Emotion and motion feedback | Completed | Manual emotion plus conversation-phase feedback |
| 15 | Face tracking | Completed | DOA wakeup turn plus face tracking runtime |
| 16 | Animation system | Completed | JSON-driven animation behavior integrated |
| 17 | Antenna sync during speech | Completed | Included in current animation/motion runtime |
| 18 | Visual gaze interaction | Completed | Current single-face-oriented runtime behavior |
| 19 | Gravity compensation teaching | Not a current runtime target | Historical exploration only |
| 20 | Environment awareness | Partial | IMU exposure exists; higher-level reactions remain limited |
| 21 | Continuous conversation | Completed | Runtime switch exposed |
| 22 | Gesture detection | Completed | Runtime detection and state publishing implemented |
| 23 | Face detection sensor | Completed | Binary sensor exposed |
| 24 | System diagnostics | Completed | Diagnostic sensor set exposed |

## Detailed Feature Notes

### Emotion And Motion Feedback

Current implemented behavior:

- Manual emotion playback through the `emotion` select entity
- Wake, listening, thinking, speaking, idle, and timer-complete state transitions drive local motion changes
- Conversation-phase reactions are non-blocking and route through the motion system rather than taking over the whole app runtime
- Home Assistant-triggered event behavior is mapped through the built-in behavior layer

Deliberately not active in the current runtime:

- Automatic emotion inference from assistant text output
- User-configured choreography layers that would break zero-config expectations

### Face Tracking

Current model:

- DOA is used once at wakeup to orient toward the speaker
- Face tracking then provides continuous visual tracking when enabled
- Body yaw follows head orientation for more natural tracking behavior
- Adaptive frame pacing is used to balance responsiveness and resource use

Implemented aspects:

- Face detector runtime
- Face tracking smoothing and interpolation
- Conversation-aware tracking behavior
- Face visibility state publishing to Home Assistant

### Animation And Speech Sway

Current animation model:

- Animation definitions are driven from `conversation_animations.json`
- Motion state transitions use the animation system plus direct motion overlays
- Speech sway provides small head motion during speech playback
- Idle behavior can combine rest pose, breathing, antenna behavior, and other built-in patterns

### Gesture Detection

Current gesture behavior:

- ONNX-based hand and gesture models are bundled in the project
- Detection can be enabled or disabled at runtime
- Results are published to Home Assistant entities
- Runtime behavior is state publishing only; gesture-driven robot actions are intentionally not the main path

### Sendspin Audio Playback

Current Sendspin behavior:

- Optional integration for synchronized audio playback
- Separate from local TTS playback path
- Automatically paused or ducked around voice assistant activity as needed
- Uses the current `aiosendspin` integration line and local buffering/backpressure handling

## Historical And Compatibility Notes

Important historical context that still matters:

- The project previously carried more legacy compatibility code and app-managed sleep/wake behavior; current runtime intentionally removed those paths
- Camera runtime evolved from a single large module into split runtime, processing, and HTTP helper modules
- Audio runtime evolved from one mixed player path into clearer local speech and Sendspin-capable music paths
- The document previously contained large box-drawing diagrams and heavily versioned planning sections; those were the main source of encoding corruption and were replaced with plain Markdown structure

## Tests Present

Current test files in `tests/`:

- `test_animation_config.py`
- `test_camera_gesture_processing.py`
- `test_command_runtime.py`
- `test_emotion_detector.py`

Current coverage is focused on animation config, command runtime behavior, gesture/camera processing, and emotion-related logic.

## Dependency Baseline

Current important runtime dependencies:

```toml
reachy-mini>=1.7.1
soundfile>=0.13.0
numpy>=2.2.5,<=2.2.5
opencv-python>=4.12.0.88
pymicro-wakeword>=2.0.0,<3.0.0
pyopen-wakeword>=1.0.0,<2.0.0
aioesphomeapi>=43.10.1
zeroconf>=0.131,<1
websockets>=12,<16
aiohttp
scipy>=1.15.3,<2.0.0
ultralytics
supervision
aiosendspin>=5.2,<6.0
onnxruntime>=1.18.0
torch==2.5.1
torchvision==0.20.1
pillow<12.0
pydantic<=2.12.5
requests>=2.33.0
```

## Current State Notes

Recent project direction reflected by the current codebase:

- The app is aligned with current Reachy Mini SDK media behavior
- Legacy compatibility paths have largely been removed
- TTS and Sendspin playback paths are separated for clearer runtime behavior
- Camera streaming is viewer-aware to reduce unnecessary CPU usage
- Idle-off mode is treated as a low-resource parked runtime rather than a legacy sleep mode

Recent version milestones relevant to the current state:

- `1.0.5` removed app-managed sleep/wake integration and aligned with newer SDK behavior
- `1.0.6` aligned the dependency baseline with newer SDK releases and improved camera snapshot/runtime handling
- `1.0.7` split local TTS playback from Sendspin-capable music playback and tightened shared audio runtime behavior
- Current uncommitted direction includes additional Sendspin alignment on the `aiosendspin 5.2` line

## Notes For Future Updates

This document should describe the current implementation, not an idealized roadmap. If a feature is disabled, optional, or runtime-gated, document it that way instead of presenting it as always active.

## Maintenance Guidance

When updating this document:

1. Prefer current code structure over historical descriptions
2. Remove outdated version snapshots rather than stacking them
3. Avoid box-drawing diagrams that are likely to suffer encoding corruption
4. Keep dependency versions aligned with `pyproject.toml`
5. Keep feature statements aligned with current runtime defaults, not planned behavior
