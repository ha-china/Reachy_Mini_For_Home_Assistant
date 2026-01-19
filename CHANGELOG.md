# Changelog

All notable changes to the Reachy Mini HA Voice project will be documented in this file.

## [Unreleased]

### Added - Core Infrastructure
- **Sleep State Management** (`core/`)
  - `DaemonStateMonitor`: Monitors robot daemon state including sleep detection
  - `SleepAwareService`: Base class for services that respond to sleep/wake
  - `SleepManager`: Coordinates sleep/wake behavior across the application
  - All services implement `suspend()`/`resume()` for proper resource management

- **Health & Memory Monitoring** (`core/`)
  - `HealthMonitor`: Service health checking with customizable intervals
  - `MemoryMonitor`: Memory usage tracking with warning thresholds
  - Automatic alerting when memory exceeds configured limits

- **Robust Error Handling** (`core/`)
  - `RobustOperationMixin`: Unified error handling with automatic recovery
  - Custom exception hierarchy for better error classification
  - Error count tracking with timeout-based reset

### Added - Motion Control
- **Antenna Control Module** (`motion/antenna.py`)
  - `AntennaController`: Manages antenna freeze/unfreeze during listening mode
  - Smooth blending for natural antenna transitions

- **Pose Composition Utilities** (`motion/pose_composer.py`)
  - `compose_full_pose()`: Combines target, animation, face tracking, and sway
  - SDK-compatible pose matrix operations
  - Body yaw calculation for natural tracking

- **Gesture Action Mapping** (`motion/gesture_actions.py`)
  - `GestureActionMapper`: Maps detected gestures to robot actions
  - Cooldown management to prevent rapid re-triggering
  - JSON configuration support (`animations/gesture_mappings.json`)

### Added - Vision Processing
- **Adaptive Frame Rate** (`vision/frame_processor.py`)
  - `AdaptiveFrameRateManager`: Optimizes CPU usage based on activity
  - High (15fps) / Low (2fps) / Idle (0.5fps) modes
  - Automatic switching based on face detection and conversation state

- **Face Tracking Interpolation** (`vision/face_tracking_interpolator.py`)
  - `FaceTrackingInterpolator`: Smooth pose interpolation when face is lost
  - Configurable delay, duration, and offset compensation
  - Uses SLERP for smooth rotation interpolation

- **MJPEG Client Tracking** (`camera_server.py`)
  - Proper client registration/unregistration
  - Resource optimization when no clients connected

### Added - Audio Processing
- **Microphone Optimization** (`audio/microphone.py`)
  - `MicrophoneOptimizer`: Configures ReSpeaker XVF3800 for voice recognition
  - `MicrophonePreferences`: User-configurable AGC, gain, and noise suppression
  - Optimized for 2-3m voice command recognition

### Added - Sound Tracking
- **DOA (Direction of Arrival) Tracking** (`audio/doa_tracker.py`)
  - `DOATracker`: Sound source localization and tracking
  - Configurable energy and angle thresholds
  - Integration with MovementManager for head turning

### Added - Home Assistant Integration
- **Event-to-Emotion Mapping** (`entities/event_emotion_mapper.py`)
  - `EventEmotionMapper`: Triggers robot emotions from HA state changes
  - Rate limiting and cooldown management
  - JSON configuration (`animations/event_mappings.json`)

- **New HA Entities**
  - DOA Tracking Enable/Disable switch
  - Sleep state sensor
  - Memory usage sensor (if monitoring enabled)

### Changed
- **CameraServer** now implements Context Manager pattern
- **CameraServer** now uses `AdaptiveFrameRateManager` module (replaced inline frame rate logic)
- **Resource Release** improved with explicit cleanup in `stop()` methods
- **Serial I/O Protection** added race condition check during sleep transition
- **Code Refactoring** - Proper module integration:
  - `movement_manager.py` now uses `AntennaController` (removed 92 lines of duplicate code)
  - `movement_manager.py` now uses `pose_composer` utilities (removed SDK availability checks)
  - `entity_registry.py` refactored with factory pattern (1112→765 lines, -31%)
  - `entity_registry.py` imports `ENTITY_KEYS` from `entities/entity_keys.py` (single source of truth)
  - `__main__.py` initializes `HealthMonitor` and `MemoryMonitor` at startup
  - `satellite.py` integrates `EventEmotionMapper` with `HomeAssistantStateResponse` handler for HA state-triggered emotions

- **New Entity Factory Module** (`entities/entity_factory.py`)
  - Declarative entity definitions with `EntityDefinition` dataclass
  - `create_entity()` factory function for all entity types
  - Predefined definition groups: `get_diagnostic_sensor_definitions()`, `get_imu_sensor_definitions()`, `get_robot_info_definitions()`, `get_pose_control_definitions()`, `get_look_at_definitions()`
  - Reduces boilerplate in entity_registry.py by 376 lines (-34%)

- **Emotion Keyword Detection** (`entities/emotion_detector.py`)
  - `EmotionKeywordDetector`: Detects emotions from LLM response text
  - JSON-configurable keyword-to-emotion mappings
  - Reduces satellite.py by 61 lines (-6%)

- **Code Size Reductions**
  - `voice_assistant.py`: 1097 → 1004 lines (-93 lines, -8%) via `MicrophoneOptimizer`
  - `camera_server.py`: 1070 → 957 lines (-113 lines, -11%) via `FaceTrackingInterpolator`
  - `satellite.py`: 1003 → 942 lines (-61 lines, -6%) via `EmotionKeywordDetector`
  - `entity_registry.py`: 1112 → 736 lines (-376 lines, -34%) via factory pattern

### Configuration Files
- `animations/gesture_mappings.json`: Gesture to action/emotion mappings
- `animations/event_mappings.json`: HA event to emotion mappings

### Fixed
- **SDK Type Compliance**: `camera_server.py` - Fixed `look_at_image()` parameter type (float→int) for SDK compliance

## [0.9.0] - 2025-01-19

### Added
- Initial release with ESPHome integration
- Voice assistant with wake word detection
- YOLO-based face tracking
- HaGRID gesture recognition
- 100Hz motion control loop
- Multi-room audio via Sendspin protocol

---

For detailed implementation notes, see [IMPROVEMENT_PLAN.md](./IMPROVEMENT_PLAN.md).
