# Changelog

All notable changes to the Reachy Mini HA Voice project will be documented in this file.

## [Unreleased]

## [0.9.9] - 2026-01-28

### Fixed
- **SDK Buffer Overflow During Idle**
  - Add SDK buffer flush on GStreamer lock timeout
  - Prevents buffer overflow during long idle periods when lock contention prevents buffer drainage
  - Audio thread flushes SDK audio buffer when lock acquisition times out
  - Camera thread flushes SDK video buffer when lock acquisition times out
  - Audio playback flushes SDK playback buffer when lock acquisition times out
  - Resolves SDK crashes during extended wake-up idle periods without conversation

### Optimized
- **Gesture Recognition Sensitivity**
  - Add GestureSmoother class with history tracking and 2-frame confirmation mechanism
  - Reduce gesture detection interval from 3 frames to 1 frame for higher frequency
  - Lower confidence threshold from 0.3 to 0.2 for improved sensitivity
  - Integrate gesture smoother into GestureDetector for stable output
  - Fix: Gesture detection now returns all detected hands instead of only the highest confidence one
  - Matches reference implementation behavior for improved detection rate
  - No conflicts with face tracking (shared frame, independent processing)

### Code Quality
- Fix Ruff linter issues (import ordering, missing newlines, __all__ sorting)
- Format code with Ruff formatter (5 files reformatted)
- Fix slice index error in gesture detection (convert coordinates to integers)

## [0.9.8] - 2026-01-27

### New
- Mute switch entity - suspends voice services only (not camera/motion)
- Disable Camera switch entity - suspends camera and AI processing
- Home Assistant connection-driven feature loading
- Automatic suspend/resume on HA disconnect/reconnect

### Fixed
- Camera disable logic - corrected inverted conditions for proper operation
- Prevent daemon crash when entering idle state
- Camera preview in Home Assistant
- SDK crash during idle - optimized audio processing to skip get_frame() when not streaming to Home Assistant, reducing GStreamer resource competition
- Add GStreamer threading lock to prevent pipeline competition between audio, playback, and camera threads
- Audio thread gets priority during conversations - bypasses lock when conversation is active

### Optimized
- Reduce log output by 30-40%
- Bundle face tracking model with package - eliminated HuggingFace download dependency, removed huggingface_hub from requirements, models now load from local package directory for offline operation
- Replace HTTP API polling with SDK Zenoh for daemon status monitoring to reduce uvicorn blocking and improve stability
- Device ID now reads /etc/machine-id directly - removed uuid.getnode() and file persistence

### Removed
- Temporarily disable emotion playback during TTS
- Unused config items (connection_timeout)

### Code Quality
- Code quality improvements

## [0.9.7] - 2026-01-20

### Fixed
- Device ID file path corrected after util.py moved to core/ subdirectory (prevents HA seeing device as new)
- Animation file path corrected (was looking in wrong directory)
- Remove hey_jarvis from required wake words (it's optional in openWakeWord/)

## [0.9.6] - 2026-01-20

### New
- Add ruff linter/formatter and mypy type checker configuration
- Add pre-commit hooks for automated code quality checks

### Fixed
- Remove duplicate resume() method in audio_player.py
- Remove duplicate connection_lost() method in satellite.py
- Store asyncio task reference in sleep_manager.py to prevent garbage collection

### Optimized
- Use dict.items() for efficient iteration in smoothing.py

## [0.9.5] - 2026-01-19

### Refactored
- Modularize codebase - new core/motion/vision/audio/entities module structure

### New
- Direct callbacks for HA sleep/wake buttons to suspend/resume services

### Optimized
- Audio processing latency - reduced chunk size from 1024 to 256 samples (64ms → 16ms)
- Audio loop delay reduced from 10ms to 1ms for faster VAD response
- Stereo to mono conversion uses first channel instead of mean for cleaner signal

### Improved
- Camera resume_from_suspend now synchronous for reliable wake from sleep
- Rotation clamping in face tracking to prevent IK collisions

## [0.9.0] - 2026-01-18

### New
- Robot state monitor for proper sleep mode handling - services pause when robot disconnects and resume on reconnect
- System diagnostics entities (CPU, memory, disk, uptime) exposed as Home Assistant diagnostic sensors
- Phase 24 with 9 diagnostic sensors (cpu_percent, cpu_temperature, memory_percent, memory_used_gb, disk_percent, disk_free_gb, uptime_hours, process_cpu_percent, process_memory_mb)

### Fixed
- Voice assistant and movement manager now properly pause during robot sleep mode instead of generating error spam

### Improved
- Graceful service lifecycle management with RobotStateMonitor callbacks

## [0.8.7] - 2026-01-18

### Fixed
- Clamp body_yaw to safe range to prevent IK collision warnings during emotion playback
- Emotion moves and face tracking now respect SDK safety limits

### Improved
- Face tracking smoothness - removed EMA smoothing (matches reference project)
- Face tracking timing updated to match reference (2s delay, 1s interpolation)

## [0.8.6] - 2026-01-18

### Fixed
- Audio buffer memory leak - added size limit to prevent unbounded growth
- Temp file leak - downloaded audio files now cleaned up after playback
- Camera thread termination timeout increased for clean shutdown
- Thread-safe draining flag using threading.Event
- Silent failures now logged for debugging

## [0.8.5] - 2026-01-18

### Fixed
- DOA turn-to-sound direction inverted - now turns correctly toward sound source
- Graceful shutdown prevents daemon crash on app stop

## [0.8.4] - 2026-01-18

### Improved
- Smooth idle animation with interpolation phase (matches reference BreathingMove)
- Two-phase animation - interpolates to neutral before oscillation
- Antenna frequency updated to 0.5Hz (was 0.15Hz) for more natural sway

## [0.8.3] - 2026-01-18

### Fixed
- Body now properly follows head rotation during face tracking
- body_yaw extracted from final head pose matrix and synced with head_yaw
- Matches reference project sweep_look behavior for natural body movement

## [0.8.2] - 2026-01-18

### Fixed
- Body now follows head rotation during face tracking - body_yaw syncs with head_yaw
- Matches reference project sweep_look behavior for natural body movement

## [0.8.1] - 2026-01-18

### Fixed
- face_detected entity now pushes state updates to Home Assistant in real-time
- Body yaw simplified to match reference project - SDK automatic_body_yaw handles collision prevention
- Idle animation now starts immediately on app launch
- Smooth antenna animation - removed pose change threshold for continuous motion

## [0.8.0] - 2026-01-17

### New
- Comprehensive emotion keyword mapping with 280+ Chinese and English keywords
- 35 emotion categories mapped to robot expressions
- Auto-trigger expressions from conversation text patterns

## [0.7.3] - 2026-01-12

### Fixed
- Revert to reference project pattern - use refractory period instead of state flags
- Remove broken _in_pipeline and _tts_playing state management
- Restore correct RUN_END event handling from linux-voice-assistant

## [0.7.2] - 2026-01-12

### Fixed
- Remove premature _tts_played reset in RUN_END event
- Ensure _in_pipeline stays True until TTS playback completes

## [0.7.1] - 2026-01-12

### Fixed
- Prevent wake word detection during TTS playback
- Add _tts_playing flag to track TTS audio state precisely

## [0.7.0] - 2026-01-12

### New
- Gesture detection using HaGRID ONNX models (18 gesture classes)
- gesture_detected and gesture_confidence entities in Home Assistant

### Fixed
- Gesture state now properly pushed to Home Assistant in real-time

### Optimized
- Aggressive power saving - 0.5fps idle mode after 30s without face
- Gesture detection only runs when face detected (saves CPU)

## [0.6.1] - 2026-01-12

### Fixed
- Prioritize MicroWakeWord over OpenWakeWord for same-name wake words
- OpenWakeWord wake words now visible in Home Assistant selection
- Stop word detection now works correctly
- STT/LLM response time improved with fixed audio chunk size

## [0.6.0] - 2026-01-11

### New
- Real-time audio-driven speech animation (SwayRollRT algorithm)
- JSON-driven animation system - all animations configurable

### Refactored
- Remove hardcoded actions, use animation offsets only

### Fixed
- TTS audio analysis now works with local playback

## [0.5.16] - 2026-01-11

### Removed
- Tap-to-wake feature (too many false triggers)

### New
- Continuous Conversation switch in Home Assistant

### Refactored
- Simplified satellite.py and voice_assistant.py

## [0.5.15] - 2026-01-11

### New
- Audio settings persistence (AGC, Noise Suppression, Tap Sensitivity)

### Refactored
- Move Sendspin mDNS discovery to zeroconf.py

### Fixed
- Tap detection not re-enabled during emotion playback in conversation

## [0.5.14] - 2026-01-11

### Fixed
- Skip ALL wake word processing when pipeline is active
- Eliminate race condition in pipeline state during continuous conversation

### Improved
- Control loop increased to 100Hz (daemon updated)

## [0.5.13] - 2026-01-10

### New
- JSON-driven animation system for conversation states
- AnimationPlayer class inspired by SimpleDances project

### Refactored
- Replace SpeechSwayGenerator and BreathingAnimation with unified animation system

## [0.5.12] - 2026-01-10

### Removed
- Deleted broken hey_reachy wake word model

### Revert
- Default wake word back to "Okay Nabu"

## [0.5.11] - 2026-01-10

### Fixed
- Reset feature extractors when switching wake words
- Add refractory period after wake word switch

## [0.5.10] - 2026-01-10

### Fixed
- Wake word models now have 'id' attribute set correctly
- Wake word switching from Home Assistant now works

## [0.5.9] - 2026-01-10

### New
- Default wake word changed to hey_reachy

### Fixed
- Wake word switching bug

## [0.5.8] - 2026-01-09

### Fixed
- Tap detection waits for emotion playback to complete
- Poll daemon API for move completion

## [0.5.7] - 2026-01-09

### New
- DOA turn-to-sound at wakeup

### Fixed
- Show raw DOA angle in Home Assistant (0-180)
- Invert DOA yaw direction

## [0.5.6] - 2026-01-08

### Fixed
- Better pipeline state tracking to prevent duplicate audio

## [0.5.5] - 2026-01-08

### New
- Prevent concurrent pipelines
- Add prompt sound for continuous conversation

## [0.5.4] - 2026-01-08

### Fixed
- Wait for RUN_END before starting new conversation

## [0.5.3] - 2026-01-08

### Fixed
- Improve continuous conversation with conversation_id tracking

## [0.5.2] - 2026-01-08

### Fixed
- Enable HA control of robot pose
- Continuous conversation improvements

## [0.5.1] - 2026-01-08

### Fixed
- Sendspin connects to music_player instead of tts_player
- Persist tap_sensitivity settings
- Pause Sendspin during voice assistant wakeup
- Sendspin prioritize 16kHz sample rate

## [0.5.0] - 2026-01-07

### New
- Face tracking with adaptive frequency
- Sendspin multi-room audio integration

### Optimized
- Shutdown mechanism improvements

## [0.4.0] - 2026-01-07

### Fixed
- Daemon stability fixes

### New
- Face tracking enabled by default

### Optimized
- Microphone settings for better sensitivity

## [0.3.0] - 2026-01-06

### New
- Tap sensitivity slider entity

### Fixed
- Music Assistant compatibility

### Optimized
- Face tracking and tap detection

## [0.2.21] - 2026-01-06

### Fixed
- Daemon crash - reduce control loop to 2Hz
- Pause control loop during audio playback

## [0.2.20] - 2026-01-06

### Revert
- Audio/satellite/voice_assistant to v0.2.9 working state

## [0.2.19] - 2026-01-06

### Fixed
- Force localhost connection mode to prevent WebRTC errors

## [0.2.18] - 2026-01-06

### Fixed
- Audio playback - restore wakeup sound
- Use push_audio_sample for TTS

## [0.2.17] - 2026-01-06

### Removed
- head_joints/passive_joints entities
- error_message to diagnostic category

## [0.2.16] - 2026-01-06

### Fixed
- TTS playback - pause recording during playback

## [0.2.15] - 2026-01-06

### Fixed
- Use play_sound() instead of push_audio_sample() for TTS

## [0.2.14] - 2026-01-06

### Fixed
- Pause audio recording during TTS playback

## [0.2.13] - 2026-01-06

### Fixed
- Don't manually start/stop media - let SDK/daemon manage it

## [0.2.12] - 2026-01-05

### Fixed
- Disable breathing animation to prevent serial port overflow

## [0.2.11] - 2026-01-05

### Fixed
- Disable wakeup sound to prevent daemon crash
- Add debug logging for troubleshooting

## [0.2.10] - 2026-01-05

### Added
- Debug logging for motion init

### Fixed
- Audio fallback samplerate

## [0.2.9] - 2026-01-05

### Removed
- DOA/speech detection - replaced by face tracking

## [0.2.8] - 2026-01-05

### New
- Replace DOA with YOLO face tracking

## [0.2.7] - 2026-01-05

### Fixed
- Add DOA caching to prevent ReSpeaker query overload

## [0.2.6] - 2026-01-05

### New
- Thread-safe ReSpeaker USB access to prevent daemon deadlock

## [0.2.4] - 2026-01-05

### Fixed
- Microphone volume control via daemon HTTP API

## [0.2.3] - 2026-01-05

### Fixed
- Daemon crash caused by conflicting pose commands
- Disable: Pose setter methods in ReachyController

## [0.2.2] - 2026-01-05

### Fixed
- Second conversation motion failure
- Reduce: Control loop from 20Hz to 10Hz
- Improve: Connection recovery (faster reconnect)

## [0.2.1] - 2026-01-05

### Fixed
- Daemon crash issue
- Optimize: Code structure

## [0.2.0] - 2026-01-05

### New
- Automatic facial expressions during conversation
- New: Emotion playback integration

### Refactored
- Integrate emotion playback into MovementManager

## [0.1.5] - 2026-01-04

### Optimized
- Code splitting and organization

### Fixed
- Program crash issues

## [0.1.0] - 2026-01-01

### New
- Initial release
- ESPHome protocol server implementation
- mDNS auto-discovery for Home Assistant
- Local wake word detection (microWakeWord)
- Voice assistant pipeline integration
- Basic motion feedback (nod, shake)

---

For detailed implementation notes, see [PROJECT_PLAN.md](./PROJECT_PLAN.md).
