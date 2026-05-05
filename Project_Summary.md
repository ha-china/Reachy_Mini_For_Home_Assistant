# Reachy Mini for Home Assistant - Project Plan (Current snapshot: v1.0.6)

## Project Overview

Integrate Home Assistant voice assistant functionality into Reachy Mini Wi-Fi robot, communicating with Home Assistant via ESPHome protocol.

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
3. **Home Assistant Centralized Management** - STT/TTS/intent configuration stays on Home Assistant side
4. **Motion Feedback** - Provide head movement and antenna animation feedback during voice interaction
5. **Project Constraints** - Strictly follow [Reachy Mini SDK](reachy_mini) architecture design and constraints
6. **Code Quality** - Follow Python development standards with consistent code style, clear structure, complete comments, comprehensive documentation, high test coverage, high code quality, readability, maintainability, extensibility, and reusability
7. **Feature Priority** - Voice conversation with Home Assistant is highest priority; other features are auxiliary and must not affect voice conversation functionality or response speed
8. **No LED Functions** - LEDs are hidden inside the robot; all LED control is ignored
9. **Preserve Functionality** - Any code modifications should optimize while preserving completed features; do not remove features to solve problems. When issues occur, prioritize solving problems after referencing examples, not adding various log outputs
10. **No App-Managed Sleep/Wake** - The app no longer manages robot sleep/wake transitions; current SDK behavior is treated as source of truth

## Technical Architecture

```
鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹?                             Reachy Mini (ARM64)                            鈹?
鈹?                                                                            鈹?
鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ AUDIO INPUT 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹? 鈹? ReSpeaker XVF3800 (16kHz)                                            鈹? 鈹?
鈹? 鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹? 鈹?
鈹? 鈹? 鈹?4-Mic Array  鈹?鈫?鈹?XVF3800 DSP                                  鈹? 鈹? 鈹?
鈹? 鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹?鈥?Hardware DSP path available                鈹? 鈹? 鈹?
鈹? 鈹?                    鈹?鈥?App currently relies on HA STT/TTS         鈹? 鈹? 鈹?
鈹? 鈹?                    鈹?鈥?DOA/VAD used by the current runtime        鈹? 鈹? 鈹?
鈹? 鈹?                    鈹?鈥?Direction of Arrival (DOA)                 鈹? 鈹? 鈹?
鈹? 鈹?                    鈹?鈥?Voice Activity Detection (VAD)             鈹? 鈹? 鈹?
鈹? 鈹?                    鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹? 鈹?
鈹? 鈹?                                     鈹?                               鈹? 鈹?
鈹? 鈹?                                     鈻?                               鈹? 鈹?
鈹? 鈹?                    鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹? 鈹?
鈹? 鈹?                    鈹?Wake Word Detection (microWakeWord)          鈹? 鈹? 鈹?
鈹? 鈹?                    鈹?鈥?"Okay Nabu" / "Hey Jarvis"                 鈹? 鈹? 鈹?
鈹? 鈹?                    鈹?鈥?Stop word detection                        鈹? 鈹? 鈹?
鈹? 鈹?                    鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹? 鈹?
鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹?                                                                            鈹?
鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ AUDIO OUTPUT 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹? 鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?   鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹? 鈹?
鈹? 鈹? 鈹?TTS Player               鈹?   鈹?Music Player (Sendspin)          鈹?鈹? 鈹?
鈹? 鈹? 鈹?鈥?Voice assistant speech 鈹?   鈹?鈥?Multi-room audio streaming     鈹?鈹? 鈹?
鈹? 鈹? 鈹?鈥?Sound effects          鈹?   鈹?鈥?Auto-discovery via mDNS        鈹?鈹? 鈹?
鈹? 鈹? 鈹?鈥?Priority over music    鈹?   鈹?鈥?Auto-pause during conversation 鈹?鈹? 鈹?
鈹? 鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?   鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹? 鈹?
鈹? 鈹?                鈹?                             鈹?                     鈹? 鈹?
鈹? 鈹?                鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?                     鈹? 鈹?
鈹? 鈹?                               鈻?                                     鈹? 鈹?
鈹? 鈹?                鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹? 鈹?
鈹? 鈹?                鈹?ReSpeaker Speaker (16kHz)                        鈹? 鈹? 鈹?
鈹? 鈹?                鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹? 鈹?
鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹?                                                                            鈹?
鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ VISION & TRACKING 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹? 鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?   鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹? 鈹?
鈹? 鈹? 鈹?Camera (VPU accelerated) 鈹?鈫? 鈹?YOLO Face Detection              鈹?鈹? 鈹?
鈹? 鈹? 鈹?鈥?MJPEG stream server    鈹?   鈹?鈥?AdamCodd/YOLOv11n-face         鈹?鈹? 鈹?
鈹? 鈹? 鈹?鈥?ESPHome Camera entity  鈹?   鈹?鈥?Adaptive frame rate:           鈹?鈹? 鈹?
鈹? 鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?   鈹?  - 15fps: conversation/face     鈹?鈹? 鈹?
鈹? 鈹?                                 鈹?  - 2fps: idle (power saving)    鈹?鈹? 鈹?
鈹? 鈹?                                 鈹?鈥?look_at_image() pose calc      鈹?鈹? 鈹?
鈹? 鈹?                                 鈹?鈥?Smooth return after face lost  鈹?鈹? 鈹?
鈹? 鈹?                                 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹? 鈹?
鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹?                                                                            鈹?
鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ MOTION CONTROL 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹? 鈹? MovementManager (50Hz Control Loop)                                  鈹? 鈹?
鈹? 鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹? 鈹?
鈹? 鈹? 鈹?Motion Layers (Priority: Move > Action > SpeechSway > Breath)  鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈹?Move Queue 鈹?鈹?Actions    鈹?鈹?SpeechSway 鈹?鈹?Breathing    鈹? 鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈹?(Emotions) 鈹?鈹?(Nod/Shake)鈹?鈹?(Voice VAD)鈹?鈹?(Idle anim)  鈹? 鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?  鈹? 鈹?
鈹? 鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹? 鈹?
鈹? 鈹?                                                                      鈹? 鈹?
鈹? 鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹? 鈹?
鈹? 鈹? 鈹?Face Tracking Offsets (Secondary Pose Overlay)                 鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈥?Pitch offset: +9掳 (down compensation)                        鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈥?Yaw offset: -7掳 (right compensation)                         鈹?  鈹? 鈹?
鈹? 鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹? 鈹?
鈹? 鈹?                                                                      鈹? 鈹?
鈹? 鈹?  State Machine: on_wakeup 鈫?on_listening 鈫?on_speaking 鈫?on_idle     鈹? 鈹?
鈹? 鈹?                                                                      鈹? 鈹?
鈹? 鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹? 鈹?
鈹? 鈹? 鈹?Body Following                                                鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈥?Body yaw syncs with head yaw for natural tracking            鈹?  鈹? 鈹?
鈹? 鈹? 鈹?鈥?Extracted from final head pose matrix                        鈹?  鈹? 鈹?
鈹? 鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?  鈹? 鈹?
鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹?                                                                            鈹?
鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ GESTURE DETECTION 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹? 鈹? HaGRID ONNX Models                                                鈹? 鈹?
鈹? 鈹? 鈥?18 gesture classes (call, like, dislike, fist, ok, palm, etc.)    鈹? 鈹?
鈹? 鈹? 鈥?Runtime result publishing only                                    鈹? 鈹?
鈹? 鈹? 鈥?Batch detection: all hands (not just highest confidence)         鈹? 鈹?
鈹? 鈹? 鈥?Detection cadence: adaptive scheduler + minimum processing FPS    鈹? 鈹?
鈹? 鈹? 鈥?No confidence filtering - all detections passed to Home Assistant鈹? 鈹?
鈹? 鈹? 鈥?Runtime switchable (default OFF, model unloaded when disabled)    鈹? 鈹?
鈹? 鈹? 鈥?Real-time state push to Home Assistant                            鈹? 鈹?
鈹? 鈹? 鈥?No conflicts with face tracking (shared frame, independent)       鈹? 鈹?
鈹? 鈹? 鈥?SDK integration: MediaBackend detection, proper resource cleanup 鈹? 鈹?
鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹?                                                                            鈹?
鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ ESPHOME SERVER 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹? 鈹? Port 6053 (mDNS auto-discovery)                                      鈹? 鈹?
鈹? 鈹? 鈥?Entity count evolves by release (sensors, controls, media, camera) 鈹? 鈹?
鈹? 鈹? 鈥?Voice Assistant pipeline integration                               鈹? 鈹?
鈹? 鈹? 鈥?Real-time state synchronization                                    鈹? 鈹?
鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹?
鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
                                       鈹?
                                       鈹?ESPHome Protocol (protobuf)
                                       鈻?
鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
鈹?                           Home Assistant                                   鈹?
鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹?
鈹? 鈹?STT Engine       鈹? 鈹?Intent Processing鈹? 鈹?TTS Engine                 鈹?鈹?
鈹? 鈹?(User configured)鈹? 鈹?(Conversation)   鈹? 鈹?(User configured)          鈹?鈹?
鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹?
鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?
```

### Software Module Architecture (v1.0.6)

```
reachy_mini_home_assistant/
鈹?
鈹溾攢鈹€ main.py                    # ReachyMiniApp entry point
鈹溾攢鈹€ __main__.py                # Standalone CLI entry point
鈹溾攢鈹€ voice_assistant.py         # Voice assistant service orchestrator
鈹溾攢鈹€ reachy_controller.py       # Reachy Mini SDK wrapper
鈹溾攢鈹€ models.py                  # Data models / preferences / server state
鈹?
鈹溾攢鈹€ core/                      # Core Infrastructure
鈹?  鈹溾攢鈹€ config.py              # Centralized nested configuration
鈹?  鈹溾攢鈹€ service_base.py        # Suspend/resume-aware service helpers
鈹?  鈹溾攢鈹€ system_diagnostics.py  # System diagnostics
鈹?  鈹溾攢鈹€ exceptions.py          # Custom exception classes
鈹?  鈹斺攢鈹€ util.py                # Utility functions
鈹?
鈹溾攢鈹€ motion/                    # Motion Control
鈹?  鈹溾攢鈹€ movement_manager.py    # 50Hz unified motion control loop
鈹?  鈹溾攢鈹€ command_runtime.py     # Command queue handling / state transitions
鈹?  鈹溾攢鈹€ control_runtime.py     # Control-loop runtime helpers
鈹?  鈹溾攢鈹€ idle_runtime.py        # Idle behavior / idle rest handling
鈹?  鈹溾攢鈹€ antenna.py             # Antenna control / freeze logic
鈹?  鈹溾攢鈹€ pose_composer.py       # Pose composition from multiple sources
鈹?  鈹溾攢鈹€ smoothing.py           # Motion smoothing algorithms
鈹?  鈹溾攢鈹€ state_machine.py       # Robot state definitions / idle config parsing
鈹?  鈹溾攢鈹€ animation_player.py    # Animation player
鈹?  鈹溾攢鈹€ emotion_moves.py       # Emotion moves
鈹?  鈹溾攢鈹€ speech_sway.py         # Speech-driven head micro-movements
鈹?  鈹斺攢鈹€ reachy_motion.py       # Reachy motion API
鈹?
鈹溾攢鈹€ vision/                    # Vision Processing
鈹?  鈹溾攢鈹€ camera_server.py       # MJPEG camera stream server facade
鈹?  鈹溾攢鈹€ camera_runtime.py      # Camera lifecycle helpers
鈹?  鈹溾攢鈹€ camera_processing.py   # Frame capture / AI processing helpers
鈹?  鈹溾攢鈹€ camera_http.py         # HTTP handlers for stream/snapshot
鈹?  鈹溾攢鈹€ head_tracker.py        # YOLO face detector
鈹?  鈹溾攢鈹€ gesture_detector.py    # HaGRID gesture detection
鈹?  鈹溾攢鈹€ face_tracking_interpolator.py  # Smooth face tracking
鈹?  鈹斺攢鈹€ frame_processor.py     # Adaptive frame rate management
鈹?
鈹溾攢鈹€ audio/                     # Audio runtime support
鈹?  鈹溾攢鈹€ audio_player.py                # AudioPlayer facade
鈹?  鈹溾攢鈹€ audio_player_shared.py         # Shared audio/sendspin constants + helpers
鈹?  鈹溾攢鈹€ audio_player_playback.py       # Playback orchestration / lifecycle
鈹?  鈹溾攢鈹€ audio_player_local.py          # Local file + fallback playback
鈹?  鈹溾攢鈹€ audio_player_stream_pcm.py     # PCM streaming playback
鈹?  鈹溾攢鈹€ audio_player_stream_decoded.py # Decoded/GStreamer streaming playback
鈹?  鈹溾攢鈹€ audio_player_sendspin.py       # Sendspin runtime integration
鈹?  鈹溾攢鈹€ microphone.py                  # Hardware audio helper / legacy tuning code
鈹?  鈹斺攢鈹€ doa_tracker.py                 # Direction of Arrival tracking
鈹?
鈹溾攢鈹€ entities/                  # Home Assistant Entities
鈹?  鈹溾攢鈹€ entity.py              # ESPHome base entity
鈹?  鈹溾攢鈹€ entity_registry.py     # ESPHome entity registry
鈹?  鈹溾攢鈹€ entity_factory.py      # Entity creation factory
鈹?  鈹溾攢鈹€ entity_keys.py         # Entity key constants
鈹?  鈹溾攢鈹€ entity_extensions.py   # Extended entity types
鈹?  鈹溾攢鈹€ runtime_entity_setup.py # Runtime/control entity wiring
鈹?  鈹溾攢鈹€ sensor_entity_setup.py # Sensor/diagnostic entity wiring
鈹?  鈹溾攢鈹€ event_emotion_mapper.py # HA event 鈫?Emotion mapping
鈹?  鈹斺攢鈹€ emotion_detector.py    # Disabled runtime path for text emotion detection
鈹?
鈹溾攢鈹€ protocol/                  # Protocol Handling
鈹?  鈹溾攢鈹€ satellite.py           # ESPHome protocol handler facade
鈹?  鈹溾攢鈹€ api_server.py          # HTTP API server
鈹?  鈹溾攢鈹€ zeroconf.py            # mDNS discovery
鈹?  鈹溾攢鈹€ entity_bridge.py       # Protocol/entity bridge helpers
鈹?  鈹溾攢鈹€ message_dispatch.py    # ESPHome message dispatch
鈹?  鈹溾攢鈹€ motion_bridge.py       # Voice 鈫?motion bridge
鈹?  鈹溾攢鈹€ session_flow.py        # Conversation lifecycle helpers
鈹?  鈹溾攢鈹€ voice_pipeline.py      # Voice event handling / TTS / stop / ducking
鈹?  鈹斺攢鈹€ wakeword_assets.py     # Wake word asset helpers
鈹?
鈹溾攢鈹€ animations/               # Animation definitions
鈹?  鈹斺攢鈹€ conversation_animations.json  # Unified built-in behavior resource file
鈹?
鈹斺攢鈹€ wakewords/                # Wake word models
    鈹溾攢鈹€ okay_nabu.json/.tflite
    鈹溾攢鈹€ hey_jarvis.json/.tflite
    鈹溾攢鈹€ alexa.json/.tflite
    鈹溾攢鈹€ hey_luna.json/.tflite
    鈹斺攢鈹€ stop.json/.tflite
```


### Current Runtime Defaults (v1.0.6)

- `idle_behavior_enabled`: user-controlled
- `sendspin_enabled`: OFF
- `face_tracking_enabled`: OFF
- `gesture_detection_enabled`: OFF
- `face_confidence_threshold`: 0.5 (persistent)
- `continuous_conversation`: user-controlled
- `Idle Behavior = OFF` means a parked no-animation state aligned to configured idle rest pose
- When `Idle Behavior = OFF`, camera server is stopped entirely to save resources
- When `Idle Behavior = ON`, camera server can run and `/snapshot` supports on-demand frame capture when cache is empty
- Idle antenna behavior: torque disabled in `IDLE`, re-enabled when leaving `IDLE`
- Voice phases and HA-triggered emotions are routed through one built-in zero-config behavior layer

When face/gesture switches are OFF, their models are unloaded to save resources.

### Current Audio Startup Note (SDK 1.7.0)

- The app now aligns to the current Reachy Mini SDK media model instead of carrying older compatibility paths.
- Camera snapshots can be fetched on demand when the MJPEG cache is empty and the camera server is still running.
- Audio block size is currently `512` samples to reduce CPU overhead versus the earlier `256`-sample path.

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
鈹溾攢鈹€ reachy_mini_ha_voice/
鈹?  鈹溾攢鈹€ __init__.py             # Package initialization (v0.9.9)
鈹?  鈹溾攢鈹€ __main__.py             # Command line entry
鈹?  鈹溾攢鈹€ main.py                 # ReachyMiniApp entry
鈹?  鈹溾攢鈹€ voice_assistant.py      # Voice assistant service (1270 lines)
鈹?  鈹溾攢鈹€ protocol/               # ESPHome protocol handling
鈹?  鈹?  鈹溾攢鈹€ __init__.py         # Module exports (13 lines)
鈹?  鈹?  鈹溾攢鈹€ satellite.py        # ESPHome protocol handler facade
鈹?  鈹?  鈹溾攢鈹€ api_server.py       # HTTP API server
鈹?  鈹?  鈹溾攢鈹€ zeroconf.py         # mDNS discovery
鈹?  鈹?  鈹溾攢鈹€ entity_bridge.py    # Protocol/entity bridge helpers
鈹?  鈹?  鈹溾攢鈹€ message_dispatch.py # ESPHome message dispatch
鈹?  鈹?  鈹溾攢鈹€ motion_bridge.py    # Voice 鈫?motion bridge
鈹?  鈹?  鈹溾攢鈹€ session_flow.py     # Conversation lifecycle helpers
鈹?  鈹?  鈹溾攢鈹€ voice_pipeline.py   # Voice event handling / TTS / stop / ducking
鈹?  鈹?  鈹斺攢鈹€ wakeword_assets.py  # Wake word asset helpers
鈹?  鈹溾攢鈹€ models.py               # Data models
鈹?  鈹斺攢鈹€ reachy_controller.py    # Reachy Mini controller wrapper (961 lines)
鈹?  鈹?
鈹?  鈹溾攢鈹€ core/                   # Core infrastructure modules
鈹?  鈹?  鈹溾攢鈹€ __init__.py         # Module exports
鈹?  鈹?  鈹溾攢鈹€ config.py           # Centralized configuration (368 lines)
鈹?  鈹?  鈹溾攢鈹€ service_base.py     # Suspend/resume-aware service helpers
鈹?  鈹?  鈹溾攢鈹€ system_diagnostics.py   # System diagnostics (250 lines)
鈹?  鈹?  鈹斺攢鈹€ exceptions.py       # Custom exception classes (68 lines)
鈹?  鈹?  鈹斺攢鈹€ util.py             # Utility functions (28 lines)
鈹?  鈹?
鈹?  鈹溾攢鈹€ motion/                 # Motion control modules
鈹?  鈹?  鈹溾攢鈹€ __init__.py         # Module exports
鈹?  鈹?  鈹溾攢鈹€ antenna.py          # Antenna freeze/unfreeze control
鈹?  鈹?  鈹溾攢鈹€ pose_composer.py    # Pose composition utilities
鈹?  鈹?  鈹溾攢鈹€ command_runtime.py  # Command queue handling / state transitions
鈹?  鈹?  鈹溾攢鈹€ control_runtime.py  # Control-loop runtime helpers
鈹?  鈹?  鈹溾攢鈹€ idle_runtime.py     # Idle behavior / idle rest handling
鈹?  鈹?  鈹溾攢鈹€ smoothing.py        # Smoothing/transition algorithms
鈹?  鈹?  鈹溾攢鈹€ state_machine.py    # State machine definitions
鈹?  鈹?  鈹溾攢鈹€ animation_player.py # Animation player
鈹?  鈹?  鈹溾攢鈹€ emotion_moves.py    # Emotion moves
鈹?  鈹?  鈹溾攢鈹€ speech_sway.py      # Speech-driven head micro-movements (338 lines)
鈹?  鈹?  鈹斺攢鈹€ reachy_motion.py    # Reachy motion API
鈹?  鈹?
鈹?  鈹溾攢鈹€ vision/                 # Vision processing modules
鈹?  鈹?  鈹溾攢鈹€ __init__.py         # Module exports (30 lines)
鈹?  鈹?  鈹溾攢鈹€ frame_processor.py  # Adaptive frame rate management (227 lines)
鈹?  鈹?  鈹溾攢鈹€ face_tracking_interpolator.py  # Face lost interpolation (253 lines)
鈹?  鈹?  鈹溾攢鈹€ gesture_detector.py  # HaGRID gesture detection
鈹?  鈹?  鈹溾攢鈹€ head_tracker.py     # YOLO face detector
鈹?  鈹?  鈹溾攢鈹€ camera_runtime.py   # Camera lifecycle helpers
鈹?  鈹?  鈹溾攢鈹€ camera_processing.py # Frame capture / AI processing helpers
鈹?  鈹?  鈹溾攢鈹€ camera_http.py      # HTTP handlers for stream/snapshot
鈹?  鈹?  鈹斺攢鈹€ camera_server.py     # MJPEG camera stream server facade
鈹?  鈹?
鈹?  鈹溾攢鈹€ audio/                  # Audio runtime modules
鈹?  鈹?  鈹溾攢鈹€ __init__.py         # Module exports (21 lines)
鈹?  鈹?  鈹溾攢鈹€ microphone.py       # Hardware audio helper / legacy tuning code
鈹?  鈹?  鈹溾攢鈹€ doa_tracker.py      # Direction of Arrival tracking
鈹?  鈹?  鈹溾攢鈹€ audio_player.py     # AudioPlayer facade
鈹?  鈹?  鈹溾攢鈹€ audio_player_shared.py # Shared audio/sendspin constants + helpers
鈹?  鈹?  鈹溾攢鈹€ audio_player_playback.py # Playback orchestration / lifecycle
鈹?  鈹?  鈹溾攢鈹€ audio_player_local.py # Local file + fallback playback
鈹?  鈹?  鈹溾攢鈹€ audio_player_stream_pcm.py # PCM streaming playback
鈹?  鈹?  鈹溾攢鈹€ audio_player_stream_decoded.py # Decoded/GStreamer streaming playback
鈹?  鈹?  鈹斺攢鈹€ audio_player_sendspin.py # Sendspin runtime integration
鈹?  鈹?
鈹?  鈹溾攢鈹€ entities/               # Home Assistant entity modules
鈹?  鈹?  鈹溾攢鈹€ __init__.py         # Module exports (38 lines)
鈹?  鈹?  鈹溾攢鈹€ entity.py           # ESPHome base entity (402 lines)
鈹?  鈹?  鈹溾攢鈹€ entity_factory.py   # Entity factory pattern (440 lines)
鈹?  鈹?  鈹溾攢鈹€ entity_keys.py      # Entity key constants (155 lines)
鈹?  鈹?  鈹溾攢鈹€ entity_extensions.py  # Extended entity types (258 lines)
鈹?  鈹?  鈹溾攢鈹€ entity_registry.py  # ESPHome entity registry
鈹?  鈹?  鈹溾攢鈹€ runtime_entity_setup.py # Runtime/control entity wiring
鈹?  鈹?  鈹溾攢鈹€ sensor_entity_setup.py # Sensor/diagnostic entity wiring
鈹?  鈹?  鈹溾攢鈹€ event_emotion_mapper.py  # HA event to emotion mapping
鈹?  鈹?  鈹斺攢鈹€ emotion_detector.py # Disabled runtime path for text emotion detection
鈹?  鈹?
鈹?  鈹溾攢鈹€ animations/             # Animation definitions
鈹?  鈹?  鈹斺攢鈹€ conversation_animations.json  # Unified animations / gestures / HA events / keyword resources
鈹?  鈹?
鈹?  鈹斺攢鈹€ wakewords/              # Wake word models
鈹?      鈹溾攢鈹€ okay_nabu.json/.tflite
鈹?      鈹溾攢鈹€ hey_jarvis.json/.tflite (openWakeWord)
鈹?      鈹溾攢鈹€ alexa.json/.tflite
鈹?      鈹溾攢鈹€ hey_luna.json/.tflite
鈹?      鈹斺攢鈹€ stop.json/.tflite   # Stop word detection
鈹?
鈹溾攢鈹€ sounds/                     # Sound effect files (auto-download)
鈹?  鈹溾攢鈹€ wake_word_triggered.flac
鈹?  鈹斺攢鈹€ timer_finished.flac
鈹溾攢鈹€ pyproject.toml              # Project configuration
鈹溾攢鈹€ README.md                   # Documentation
鈹溾攢鈹€ changelog.json              # Version changelog
鈹斺攢鈹€ PROJECT_PLAN.md             # Project plan
```

## Dependencies

```toml
dependencies = [
    "reachy-mini>=1.7.0",
    "soundfile>=0.13.0",
    "numpy>=2.2.5,<=2.2.5",
    "opencv-python>=4.12.0.88",
    "pymicro-wakeword>=2.0.0,<3.0.0",
    "pyopen-wakeword>=1.0.0,<2.0.0",
    "aioesphomeapi>=43.10.1",
    "zeroconf>=0.131,<1",
    "websockets>=12,<16",
    "aiohttp",
    "scipy>=1.15.3,<2.0.0",
    "ultralytics",
    "supervision",
    "aiosendspin>=5.1,<6.0",
    "onnxruntime>=1.18.0",
    "torch==2.5.1",
    "torchvision==0.20.1",
    "pillow<12.0",
    "pydantic<=2.12.5",
    "requests>=2.33.0",
    "gstreamer-bundle==1.28.1; sys_platform != 'linux'",
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
   - Or manually add: Settings 閳?Devices & Services 閳?Add Integration 閳?ESPHome

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
| `Switch` | `idle_behavior_enabled` | `set_idle_behavior_enabled()` | off=parked/on=idle runtime enabled | Unified idle behavior toggle |
| `Number` | `head_x` | `goto_target(head=...)` | 卤50mm | Head X position control |
| `Number` | `head_y` | `goto_target(head=...)` | 卤50mm | Head Y position control |
| `Number` | `head_z` | `goto_target(head=...)` | 卤50mm | Head Z position control |
| `Number` | `head_roll` | `goto_target(head=...)` | -40掳 ~ +40掳 | Head roll angle control |
| `Number` | `head_pitch` | `goto_target(head=...)` | -40掳 ~ +40掳 | Head pitch angle control |
| `Number` | `head_yaw` | `goto_target(head=...)` | -180掳 ~ +180掳 | Head yaw angle control |
| `Number` | `body_yaw` | `goto_target(body_yaw=...)` | -160掳 ~ +160掳 | Body yaw angle control |
| `Number` | `antenna_left` | `goto_target(antennas=...)` | -90掳 ~ +90掳 | Left antenna angle control |
| `Number` | `antenna_right` | `goto_target(antennas=...)` | -90掳 ~ +90掳 | Right antenna angle control |

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
| `Sensor` | `doa_angle` | `DoAInfo.angle` | Sound source direction angle (鎺? |
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
| `Sensor` | `imu_accel_x` | `mini.imu["accelerometer"][0]` | X-axis acceleration (m/s铏? |
| `Sensor` | `imu_accel_y` | `mini.imu["accelerometer"][1]` | Y-axis acceleration (m/s铏? |
| `Sensor` | `imu_accel_z` | `mini.imu["accelerometer"][2]` | Z-axis acceleration (m/s铏? |
| `Sensor` | `imu_gyro_x` | `mini.imu["gyroscope"][0]` | X-axis angular velocity (rad/s) |
| `Sensor` | `imu_gyro_y` | `mini.imu["gyroscope"][1]` | Y-axis angular velocity (rad/s) |
| `Sensor` | `imu_gyro_z` | `mini.imu["gyroscope"][2]` | Z-axis angular velocity (rad/s) |
| `Sensor` | `imu_temperature` | `mini.imu["temperature"]` | IMU temperature (鎺矯) |

#### Current Runtime Control and Sensor Entities

| Phase | ESPHome Entity Type | Name | Description |
|------|---------------------|------|-------------|
| 1 | `Switch` | `mute` | Suspend/resume the voice pipeline |
| 1 | `Switch` | `camera_disabled` | Disable/enable camera runtime |
| 1 | `Switch` | `idle_behavior_enabled` | Unified idle motion / antenna / micro-actions toggle |
| 1 | `Switch` | `sendspin_enabled` | Enable/disable Sendspin playback integration |
| 1 | `Switch` | `face_tracking_enabled` | Enable/disable face tracking models |
| 1 | `Switch` | `gesture_detection_enabled` | Enable/disable gesture detection models |
| 1 | `Number` | `face_confidence_threshold` | Face tracking confidence threshold (0-1) |
| 2 | `Binary Sensor` | `services_suspended` | Runtime suspension state |
| 8 | `Select` | `emotion` | Manual emotion trigger |
| 10 | `Camera` | `camera` | ESPHome camera entity / live preview |
| 21 | `Switch` | `continuous_conversation` | Multi-turn conversation mode |
| 22 | `Text Sensor` | `gesture_detected` | Current detected gesture |
| 22 | `Sensor` | `gesture_confidence` | Current gesture confidence |
| 23 | `Binary Sensor` | `face_detected` | Face currently visible |

> **Note**: Head position (x/y/z) and angles (roll/pitch/yaw), body yaw, antenna angles are all **controllable** entities,
> using `Number` type for bidirectional control. Call `goto_target()` when setting new values, call `get_current_head_pose()` etc. when reading current values.

### Implementation Priority

1. **Phase 1 - Basic Status and Volume** (High Priority) 閴?**Completed**
   - [x] `daemon_state` - Daemon status sensor
   - [x] `backend_ready` - Backend ready status
   - [x] `error_message` - Error message
   - [x] `speaker_volume` - Speaker volume control

2. **Phase 2 - Runtime State** (High Priority) 鉁?**Completed**
   - [x] `services_suspended` - Service suspension state sensor
   - [x] App-managed sleep/wake entities removed from the current runtime

3. **Phase 3 - Pose Control** (Medium Priority) 閴?**Completed**
   - [x] `head_x/y/z` - Head position control
   - [x] `head_roll/pitch/yaw` - Head angle control
   - [x] `body_yaw` - Body yaw angle control
   - [x] `antenna_left/right` - Antenna angle control

4. **Phase 4 - Gaze Control** (Medium Priority) 閴?**Completed**
   - [x] `look_at_x/y/z` - Gaze point coordinate control

5. **Phase 5 - DOA (Direction of Arrival)** 閴?**Re-added for wakeup turn-to-sound**
   - [x] `doa_angle` - Sound source direction (degrees, 0-180鎺? where 0鎺?left, 90鎺?front, 180鎺?right)
   - [x] `speech_detected` - Speech detection status
   - [x] Turn-to-sound at wakeup (robot turns toward speaker when wake word detected)
   - [x] Direction correction: `yaw = 锜?2 - doa` (fixed left/right inversion)
   - Note: DOA only read once at wakeup to avoid daemon pressure; face tracking takes over after

6. **Phase 6 - Diagnostic Information** (Low Priority) 閴?**Completed**
   - [x] `control_loop_frequency` - Control loop frequency
   - [x] `sdk_version` - SDK version
   - [x] `robot_name` - Robot name
   - [x] `wireless_version` - Wireless version flag
   - [x] `simulation_mode` - Simulation mode flag
   - [x] `wlan_ip` - Wireless IP address

7. **Phase 7 - IMU Sensors** (Optional, wireless version only) 閴?**Completed**
   - [x] `imu_accel_x/y/z` - Accelerometer
   - [x] `imu_gyro_x/y/z` - Gyroscope
   - [x] `imu_temperature` - IMU temperature

8. **Phase 8 - Emotion Control** 閴?**Completed**
    - [x] `emotion` - Emotion selector (Happy/Sad/Angry/Fear/Surprise/Disgust)

9. **Phase 10 - Camera Integration** 閴?**Completed**
    - [x] `camera` - ESPHome Camera entity (live preview)

10. **Phase 11 - LED Control** 閴?**Disabled (LEDs hidden inside robot)**
    - [ ] `led_brightness` - LED brightness (0-100%) - Commented out
    - [ ] `led_effect` - LED effect (off/solid/breathing/rainbow/doa) - Commented out
    - [ ] `led_color_r/g/b` - LED RGB color (0-255) - Commented out

11. **Phase 13 - Sendspin Audio Playback Support** 閴?**Completed**
    - [x] `sendspin_enabled` - Sendspin switch (Switch)
    - [x] AudioPlayer integrates aiosendspin library
    - [x] Local music/sendspin path coexists with voice playback and is auto-paused during conversation

12. **Phase 21 - Continuous Conversation** 閴?**Completed**
    - [x] `continuous_conversation` - Conversation continuation switch

13. **Phase 22 - Gesture Detection** 鉁?**Completed (current runtime behavior)**
    - [x] `gesture_detected` - Detected gesture name (Text Sensor)
    - [x] `gesture_confidence` - Gesture detection confidence % (Sensor)
    - [x] HaGRID ONNX models: hand_detector.onnx + crops_classifier.onnx
    - [x] Real-time state push to Home Assistant
    - [x] Runtime gesture result publishing only (no gesture-driven robot actions)
    - [x] Runtime toggle supported (default OFF, model unload on disable)
    - [x] Batch detection: returns all detected hands (not just highest confidence)
    - [x] Minimum processing cadence preserved for responsiveness
    - [x] No conflicts with face tracking (shared frame, independent processing)
    - [x] SDK integration: MediaBackend detection, proper resource cleanup on shutdown
    - [x] 18 supported gestures:
      | Gesture | Emoji | Gesture | Emoji |
      |---------|-------|---------|-------|
      | call | 棣冾樉 | like | 棣冩啢 |
      | dislike | 棣冩啣 | mute | 棣冦亱 |
      | fist | 閴?| ok | 棣冩啠 |
      | four | 棣冩瀾閿?| one | 閳芥繐绗?|
      | palm | 閴?| peace | 閴佸矉绗?|
      | peace_inverted | 棣冩暰閴佸矉绗?| rock | 棣冾樈 |
      | stop | 棣冩磧 | stop_inverted | 棣冩暰棣冩磧 |
      | three | 3閿斿繆鍎?| three2 | 棣冾檮 |
      | two_up | 閴佸矉绗嶉埥婵撶瑣 | two_up_inverted | 棣冩暰閴佸矉绗嶉埥婵撶瑣 |

14. **Phase 23 - Face Detection** 閴?**Completed**
    - [x] `face_detected` - Face visibility sensor

15. **Phase 24 - System Diagnostics** 閴?**Completed**
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

## 棣冨竴 Current Runtime Entity Coverage

**Total Completed: See runtime registry (count evolves with releases)**
- Phase 1: 10 entities (status, zero-config runtime switches, volume)
- Phase 2: runtime state entities only (`services_suspended`; sleep entities removed)
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

## 棣冩畬 Voice Assistant Enhancement Features Implementation Status

### Phase 14 - Emotion and Motion Feedback 閴?
**Current Status**: Manual emotion playback and non-blocking motion feedback are implemented. Automatic keyword-based emotion triggering is currently disabled in the runtime.

**Implemented Features**:
- 閴?Phase 8 Emotion Selector entity (`emotion`)
- 閴?`_play_emotion()` queues emotion moves through `MovementManager`
- 閴?Wake/listen/think/speak/idle motion transitions are non-blocking
- 閴?Timer-finished motion feedback is implemented
- 閴?Gesture detection publishes recognized gesture label and confidence to Home Assistant entities
- 閴?Voice phases and HA state reactions share one built-in behavior dispatcher

**Current Behavior**:

| Voice Assistant Event | Actual Action | Implementation Status |
|----------------------|---------------|----------------------|
| Wake word detected | Turn toward sound source + listening pose | 閴?Implemented |
| Listening | Attentive listening state | 閴?Implemented |
| Thinking | Thinking state animation | 閴?Implemented |
| Speaking | Speech-reactive motion | 閴?Implemented |
| Timer completed | Alert shake motion | 閴?Implemented |
| Manual emotion trigger | Play via ESPHome `emotion` entity | 閴?Implemented |

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

### Phase 15 - Face Tracking (Complements DOA Turn-to-Sound) 閴?**Completed**

**Goal**: Implement natural face tracking so robot looks at speaker during conversation.

**Design Decision**:
- 閴?DOA (Direction of Arrival): Used once at wakeup to turn toward sound source
- 閴?YOLO face detection: Takes over after initial turn for continuous tracking
- 閴?Body follows head rotation: Body yaw automatically syncs with head yaw for natural tracking
- Reason: DOA provides quick initial orientation, face tracking provides accurate continuous tracking, body following enables natural whole-body tracking similar to human behavior

**Wakeup Turn-to-Sound Flow**:
1. Wake word detected 閳?Read DOA angle once (avoid daemon pressure)
2. If DOA angle > 10鎺? Turn head toward sound source (80% of angle, conservative)
3. Face tracking takes over for continuous tracking during conversation

**Implemented Features**:

| Feature | Description | Implementation Location | Status |
|---------|-------------|------------------------|--------|
| DOA turn-to-sound | Turn toward speaker at wakeup | `protocol/satellite.py:_turn_to_sound_source()` | 閴?Implemented |
| YOLO face detection | Uses `AdamCodd/YOLOv11n-face-detection` model | `vision/head_tracker.py` | 閴?Implemented |
| Adaptive frame rate tracking | 15fps during conversation, 2fps when idle without face | `camera_server.py` | 閴?Implemented |
| look_at_image() | Calculate target pose from face position | `camera_server.py` | 閴?Implemented |
| Smooth return to neutral | Smooth return within 1 second after face lost | `camera_server.py` | 閴?Implemented |
| face_tracking_offsets | As secondary pose overlay to motion control | `movement_manager.py` | 閴?Implemented |
| Body follows head rotation | Body yaw syncs with head yaw extracted from final pose matrix | `motion/movement_manager.py:_compose_final_pose()` | 閴?Implemented (v0.8.3) |
| DOA entities | `doa_angle` and `speech_detected` exposed to Home Assistant | `entity_registry.py` | 閴?Implemented |
| face_detected entity | Binary sensor for face detection state | `entity_registry.py` | 閴?Implemented |
| Model download retry | 3 retries, 5 second interval | `head_tracker.py` | 閴?Implemented |
| Conversation mode integration | Auto-switch tracking frequency on voice assistant state change | `satellite.py` | 閴?Implemented |

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
    # prevention by clamping relative angle to max 65鎺? not active following
    body_yaw = final_head_yaw

    return final_head, (antenna_right, antenna_left), body_yaw
```

**Body Following Head Rotation (v0.8.3)**:
- SDK's `automatic_body_yaw` is only **collision protection**, not active body following
- The `inverse_kinematics_safe` function with `max_relative_yaw=65鎺砢 only prevents head-body collision
- To enable natural body following, `body_yaw` must be explicitly set to match `head_yaw`
- Body yaw is extracted from final head pose matrix using scipy's `R.from_matrix().as_euler('xyz')`
- This matches the reference project's `sweep_look.py` behavior where `target_body_yaw = head_yaw`


### Phase 16 - Cartoon Style Motion Mode (Partial) 棣冪厸

**Goal**: Use SDK interpolation techniques for more expressive robot movements.

**SDK Support**: `InterpolationTechnique` enum
- `LINEAR` - Linear, mechanical feel
- `MIN_JERK` - Minimum jerk, natural and smooth (default)
- `EASE_IN_OUT` - Ease in-out, elegant
- `CARTOON` - Cartoon style, with bounce effect, lively and cute

**Implemented Features**:
- 閴?50Hz unified control loop (`motion/movement_manager.py`) - Current stable frequency
- 閴?JSON-driven animation system (`AnimationPlayer`) - Inspired by SimpleDances project
- 閴?Conversation state animations (idle/listening/thinking/speaking)
- 閴?Pose change detection - Only send commands on significant changes (threshold 0.005)
- 閴?State query caching - 2s TTL, reduces daemon load
- 閴?Smooth interpolation (ease in-out curve)
- 閴?Command queue mode - Thread-safe external API
- 閴?Error throttling - Prevents log explosion
- 閴?Connection health monitoring - Auto-detect and recover from connection loss

**Animation System (v0.5.13)**:
- `AnimationPlayer` class loads animations from `conversation_animations.json`
- Each animation defines: pitch/yaw/roll amplitudes, position offsets, antenna movements, frequency
- Smooth transitions between animations (configurable duration)
- State-to-animation mapping: idle閳姕dle, listening閳姡istening, thinking閳姲hinking, speaking閳姱peaking

**Not Implemented**:
- 閴?Dynamic interpolation technique switching (CARTOON/EASE_IN_OUT etc.)
- 閴?Exaggerated cartoon bounce effects

**Code Locations**:
- `motion/animation_player.py` - AnimationPlayer class
- `animations/conversation_animations.json` - Animation definitions
- `motion/movement_manager.py` - 50Hz control loop with animation integration

**Scene Implementation Status**:

| Scene | Recommended Interpolation | Effect | Status |
|-------|--------------------------|--------|--------|
| Wake nod | `CARTOON` | Lively bounce effect | 閴?Not implemented |
| Thinking head up | `EASE_IN_OUT` | Elegant transition | 閴?Implemented (smooth interpolation) |
| Speaking micro-movements | `MIN_JERK` | Natural and fluid | 閴?Implemented (SpeechSway) |
| Error head shake | `CARTOON` | Exaggerated denial | 閴?Not implemented |
| Return to neutral | `MIN_JERK` | Smooth return | 閴?Implemented |
| Idle breathing | - | Subtle sense of life | 閴?Implemented (BreathingAnimation) |

### Phase 17 - Antenna Sync Animation During Speech (Completed) 閴?
**Goal**: Antennas sway with audio rhythm during TTS playback, simulating "speaking" effect.

**Implemented Features**:
- 閴?JSON-driven animation system with antenna movements
- 閴?Different antenna patterns: "both" (sync), "wiggle" (opposite phase)
- 閴?State-specific antenna animations (listening/thinking/speaking)
- 閴?Smooth transitions between animation states
- 閴?v1.0.0 idle refinement: idle antenna sway disabled while conversation-state antenna behaviors are retained
- 閴?v1.0.0 hardware refinement: antenna torque disabled in `IDLE` to reduce idle chatter/noise

**Code Locations**:
- `motion/animation_player.py` - AnimationPlayer with antenna offset calculation
- `animations/conversation_animations.json` - Antenna amplitude and pattern definitions
- `motion/movement_manager.py` - Antenna offset composition in final pose

### Phase 18 - Visual Gaze Interaction (Single-face only) 閴?
**Goal**: Use camera to detect faces for eye contact.

**SDK Support**:
- `look_at_image(u, v)` - Look at point in image
- `look_at_world(x, y, z)` - Look at world coordinate point
- `media.get_frame()` - Get camera frame (閴?Already implemented in `vision/camera_server.py:146`)

**Current Status**:

| Feature | Description | Status |
|---------|-------------|--------|
| Face detection | YOLO-based face detection (`AdamCodd/YOLOv11n-face-detection`) | 閴?Implemented |
| Eye tracking | Robot tracks detected face during conversation/active mode | 閴?Implemented |
| Idle scanning | Random look-around in idle cycles (switch-controlled) | 閴?Implemented |

> Scope note: Current implementation is intentionally single-face tracking for stability and device performance.

### Phase 19 - Gravity Compensation Interactive Mode (Historical / Not Current Target)

This was an exploration direction for manual teaching workflows.

**Current Runtime Position**:
- The zero-config runtime does not depend on a teaching flow
- No user-facing teaching interaction is exposed as a core feature
- If gravity-compensation support is revisited, it should remain optional and not become a required setup path

### Phase 20 - Environment Awareness Response (Partial) 棣冪厸

**Goal**: Use IMU sensors to sense environment changes and respond.

**SDK Support**:
- 閴?`mini.imu["accelerometer"]` - Accelerometer (Phase 7 implemented as entity)
- 閴?`mini.imu["gyroscope"]` - Gyroscope (Phase 7 implemented as entity)

**Implemented Features**:

| Feature | Description | Status |
|---------|-------------|--------|
| Continuous conversation | Controlled via Home Assistant switch | 閴?Implemented |
| IMU sensor entities | Accelerometer and gyroscope exposed to HA | 閴?Implemented |

> **Note**: Tap-to-wake feature was removed in v0.5.16 due to false triggers from robot movement. Continuous conversation is now controlled via Home Assistant switch.

**Not Implemented**:

| Detection Event | Response Action | Status |
|-----------------|-----------------|--------|
| Being shaken | Play dizzy action + voice "Don't shake me~" | 閴?Not implemented |
| Tilted/fallen | Play help action + voice "I fell, help me" | 閴?Not implemented |
| Long idle | Enter sleep animation | 閴?Not implemented |

### Phase 21 - Home Assistant Orchestration Scope

The current runtime already exposes the main zero-config controls needed by Home Assistant:

- `services_suspended`
- `idle_behavior_enabled`
- `continuous_conversation`
- `emotion`
- gesture / face / diagnostic sensors

More elaborate scene orchestration remains intentionally outside the core runtime scope unless it can be delivered without introducing user configuration burden.


---

## 棣冩惓 Feature Implementation Summary

### 閴?Completed Features

#### Core Voice Assistant (Phase 1-12)
- **ESPHome entities** - Core phases implemented (Phase 11 LED intentionally disabled); exact count evolves by release
- **Basic voice interaction** - Wake word detection (microWakeWord/openWakeWord), STT/TTS integration
- **Motion feedback** - Nod, shake, gaze and other basic actions
- **Audio path** - local wake word / stop word detection plus HA-managed STT/TTS
- **Camera stream** - MJPEG live preview with ESPHome Camera entity

#### Extended Features (Phase 13-22)
- **Phase 13** 閴?- Sendspin multi-room audio support
- **Phase 14** 閴?- Manual emotion playback + non-blocking motion feedback
- **Phase 15** 閴?- Face tracking with body following (DOA + YOLO + body_yaw sync)
- **Phase 16** 閴?- JSON-driven animation system (50Hz control loop)
- **Phase 17** 閴?- Antenna sync animation during speech
- **Phase 22** 閴?- Gesture detection (HaGRID ONNX, 18 gestures)

### 棣冪厸 Partially Implemented Features

- **Phase 20** - IMU sensor entities are exposed; higher-level trigger logic is intentionally minimal

### 閴?Not Implemented Features

- Zero-config scene orchestration beyond the provided runtime switches and blueprint defaults

---

## Feature Priority Summary (Updated v1.0.6)

### Completed 鉁?
- 鉁?**Phase 1-12**: Core ESPHome entities and voice assistant
- 鉁?**Phase 13**: Sendspin audio playback
- 鉁?**Phase 14**: Emotion playback and motion feedback
- 鉁?**Phase 15**: Face tracking with body following
- 鉁?**Phase 16**: JSON-driven animation system
- 鉁?**Phase 17**: Antenna sync animation + v1.0.0 idle antenna behavior refinements
- 鉁?**Phase 21**: Continuous conversation switch
- 鉁?**Phase 22**: Gesture detection
- 鉁?**Phase 23**: Face detection sensor
- 鉁?**Phase 24**: System diagnostics entities

### Partial 棣冪厸
- 棣冪厸 **Phase 20**: Environment awareness (IMU entities done, triggers pending)

### Not Implemented 閴?- 閴?Zero-config scene orchestration layer beyond current runtime behavior

---

## 棣冩惐 Completion Statistics

| Phase | Status | Completion | Notes |
|-------|--------|------------|-------|
| Phase 1-12 | 閴?Complete | 100% | Core ESPHome entities implemented (Phase 11 LED intentionally disabled) |
| Phase 13 | 閴?Complete | 100% | Sendspin audio playback support |
| Phase 14 | 閴?Complete | 100% | Manual emotion playback and non-blocking motion feedback |
| Phase 15 | 閴?Complete | 100% | Face tracking with DOA, YOLO detection, body follows head |
| Phase 16 | 閴?Complete | 100% | JSON-driven animation system (50Hz control loop) |
| Phase 17 | 閴?Complete | 100% | Antenna sync animation during speech |
| Phase 18 | 閴?Complete | 100% | Single-face visual gaze interaction with idle scanning |
| Phase 19 | Not a current runtime target | - | Historical planning item, not part of the zero-config runtime model |
| Phase 20 | 馃煛 Partial | 30% | IMU sensors exposed, missing trigger logic |
| Phase 21 | 鉁?Complete | 100% | Continuous conversation switch implemented |
| Phase 22 | 鉁?Complete | 100% | Gesture detection with HaGRID ONNX models |
| Phase 23 | 鉁?Complete | 100% | Face detection sensor exposed |
| Phase 24 | 鉁?Complete | 100% | System diagnostics entities (9 sensors) |
| **v0.9.5** | 鉁?Complete | 100% | Modular architecture refactoring |
| **v1.0.0** | 鉁?Complete | 100% | Runtime toggles/persistence (Sendspin, face, gesture, confidence) + idle and gesture stability updates |

**Overall Completion**: current zero-config runtime path is functionally complete; remaining gaps are optional orchestration ideas rather than missing core runtime features.


---

## 棣冩暋 Daemon Crash Fix (2025-01-05)

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
| Control message frequency | ~100 msg/s | ~20 msg/s | 閳?80% |
| State query frequency | ~50 msg/s | ~5 msg/s | 閳?90% |
| Total Zenoh messages | ~150 msg/s | ~25 msg/s | 閳?83% |
| Daemon CPU load | Sustained high load | Normal load | Significantly reduced |
| Expected stability | Crash within hours | Stable for days | Major improvement |

### Related Files
- `DAEMON_CRASH_FIX_PLAN.md` - Detailed fix plan and test plan
- `movement_manager.py` - Control loop optimization
- `reachy_controller.py` - State query caching

### Future Optimization Suggestions
1. 鈴?Dynamic frequency adjustment - 50Hz during motion, 5Hz when idle
2. 鈴?Batch state queries - Get all states at once
3. 鈴?Further runtime efficiency tuning after real usage profiling

---

## 棣冩暋 Daemon Crash Deep Fix (2026-01-07)

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
   - 20Hz 鑴?3 messages = 60 messages/second
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
# 0.005 rad 閳?0.29 degrees, still smooth enough
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

## 棣冩暋 Microphone Sensitivity Optimization (2026-01-07)

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

## 棣冩暋 v0.5.1 Bug Fixes (2026-01-08)

### Issue 1: Music Not Resuming After Voice Conversation

**Fix**: Sendspin now connects to `music_player` instead of `tts_player`

### Issue 2: Audio Conflict During Voice Assistant Wakeup

**Fix**: Added `pause_sendspin()` and `resume_sendspin()` methods to `audio/audio_player.py`

### Issue 3: Sendspin Sample Rate Optimization

**Fix**: Prioritize 16kHz in Sendspin supported formats (hardware limitation)

---

## 棣冩暋 v0.5.15 Updates (2026-01-11)

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
    "accelerometer": [x, y, z],  # m/s铏?
    "gyroscope": [x, y, z],      # rad/s
    "quaternion": [w, x, y, z],  # Attitude quaternion
    "temperature": float         # 鎺矯
}

# Safety limits
HEAD_PITCH_ROLL_LIMIT = [-40鎺? +40鎺砞
HEAD_YAW_LIMIT = [-180鎺? +180鎺砞
BODY_YAW_LIMIT = [-160鎺? +160鎺砞
YAW_DELTA_MAX = 65鎺? # Max difference between head and body yaw
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

## 棣冩暋 Code Refactoring & Improvement Plan (v0.9.5)

> Comprehensive improvement plan based on code analysis
> Target Platform: Raspberry Pi CM4 (4GB RAM, 4-core CPU)

### Code Size Statistics (Updated 2026-01-19)

| File | Original | Current | Status |
|------|----------|---------|--------|
| `movement_manager.py` | 1205 | 1260 | 閳跨媴绗?Modularized but still large |
| `voice_assistant.py` | 1097 | 1270 | 閴?Enhanced with new features |
| `satellite.py` | 1003 | 1022 | 閴?Optimized (-2%) |
| `camera_server.py` | 1070 | 1009 | 閴?Optimized (-6%) |
| `reachy_controller.py` | 878 | 961 | 閴?Enhanced |
| `entity_registry.py` | 1129 | 844 | 閴?Optimized (-25%) |
| `audio_player.py` | 599 | 679 | 閴?Acceptable |
| `core/service_base.py` | - | 552 | 棣冨晭 New module |
| `entities/entity_factory.py` | - | 440 | 棣冨晭 New module |

> **Optimization Notes**:
> - `entity_registry.py`: Factory pattern refactoring reduced 285 lines
> - `camera_server.py`: Using `FaceTrackingInterpolator` module reduced 61 lines
> - `protocol/satellite.py`: Runtime paths are now centered on voice state handling and HA event reactions
> - New modular architecture with 6 sub-packages: `core/`, `motion/`, `vision/`, `audio/`, `entities/`, `protocol/`

### New Module List (Updated 2026-01-19)

| Directory | Module | Lines | Description |
|-----------|--------|-------|-------------|
| `core/` | `config.py` | 454 | Centralized nested configuration |
| `core/` | `service_base.py` | 552 | Suspend/resume service helpers + RobustOperationMixin |
| `core/` | `system_diagnostics.py` | 250 | System diagnostics |
| `core/` | `exceptions.py` | 68 | Custom exception classes |
| `core/` | `util.py` | 28 | Utility functions |
| `motion/` | `antenna.py` | - | Antenna freeze/unfreeze control |
| `motion/` | `pose_composer.py` | - | Pose composition utilities |
| `motion/` | `command_runtime.py` | - | Command queue handling / state transitions |
| `motion/` | `control_runtime.py` | - | Control-loop runtime helpers |
| `motion/` | `idle_runtime.py` | - | Idle behavior / idle rest handling |
| `motion/` | `state_machine.py` | - | State machine definitions |
| `motion/` | `smoothing.py` | - | Smoothing/transition algorithms |
| `motion/` | `animation_player.py` | - | Animation player |
| `motion/` | `emotion_moves.py` | - | Emotion moves |
| `motion/` | `speech_sway.py` | 338 | Speech-driven head micro-movements |
| `motion/` | `reachy_motion.py` | - | Reachy motion API |
| `vision/` | `frame_processor.py` | 227 | Adaptive frame rate management |
| `vision/` | `face_tracking_interpolator.py` | 253 | Face lost interpolation |
| `vision/` | `gesture_smoother.py` | 80 | Historical gesture smoothing module; current runtime no longer depends on it |
| `vision/` | `gesture_detector.py` | 285 | HaGRID gesture detection |
| `vision/` | `head_tracker.py` | 367 | YOLO face detector |
| `vision/` | `camera_server.py` | 1009 | MJPEG camera stream server facade |
| `audio/` | `doa_tracker.py` | 206 | Direction of Arrival tracking |
| `audio/` | `microphone.py` | 219 | Hardware audio helper / legacy tuning code |
| `audio/` | `audio_player.py` | facade | AudioPlayer facade (split into playback/sendspin/local streaming modules) |
| `entities/` | `entity.py` | 402 | ESPHome base entity |
| `entities/` | `entity_factory.py` | 440 | Entity factory pattern |
| `entities/` | `entity_keys.py` | 155 | Entity key constants |
| `entities/` | `entity_extensions.py` | 258 | Extended entity types |
| `entities/` | `event_emotion_mapper.py` | 351 | HA event to emotion mapping |
| `protocol/` | `satellite.py` | 1022 | ESPHome protocol handler |
| `protocol/` | `api_server.py` | 172 | HTTP API server |
| `protocol/` | `zeroconf.py` | - | mDNS discovery |

### Improvement Plan Status

#### Phase 1: Runtime Suspend/Resume Foundation 鉁?Complete

- [x] Create `core/service_base.py` - runtime suspend/resume service helpers
- [x] All required services implement `suspend()` / `resume()` methods where needed
- [x] Historical app-managed sleep/wake flow was later removed to align with the current SDK

#### Phase 2: Code Modularization 閴?Complete

- [x] Create new directory structure (`core/`, `motion/`, `audio/`, `vision/`, `entities/`)
- [x] Extract from `movement_manager.py` 閳?`motion/antenna.py`, `motion/pose_composer.py`
- [x] Extract from `camera_server.py` 閳?`vision/frame_processor.py`, `vision/face_tracking_interpolator.py`
- [x] Extract from `entity_registry.py` 閳?`entities/entity_factory.py`, `entities/entity_keys.py`
- [x] Create `core/config.py` for centralized configuration
- [x] Ensure no circular dependencies

#### Phase 3: Stability & Performance 閴?Complete

- [x] Create `core/exceptions.py` - Custom exception classes
- [x] Implement `RobustOperationMixin` - Unified error handling
- [x] `CameraServer` implements Context Manager pattern
- [x] Improve `CameraServer` resource cleanup
- [x] Fix MJPEG client tracking (proper register/unregister)
- [x] Historical health/memory monitor modules were added during earlier SDK instability periods
- [x] Health/memory monitor modules were later removed after runtime simplification
- [ ] Long-running stability test (24h+)

#### Phase 4: Feature Enhancements 閴?Complete

- [x] Historical gesture-action runtime path explored
- [x] Gesture runtime later simplified to publish recognition results only
- [x] Create `audio/doa_tracker.py` - DOATracker
- [x] Implement sound source tracking with motion control integration
- [x] Create `entities/event_emotion_mapper.py` - EventEmotionMapper
- [x] Fold HA event behavior config into `animations/conversation_animations.json`
- [x] Add DOA tracking toggle HA entity

### SDK Compatibility Verification 閴?Passed

| API Call | Status | Notes |
|----------|--------|-------|
| `set_target(head, antennas, body_yaw)` | 閴?| Correct usage |
| `goto_target()` | 閴?| Correct usage |
| `look_at_image(u: int, v: int)` | 閴?| Fixed float閳姕nt |
| `create_head_pose(degrees=False)` | 閴?| Using radians |
| `compose_world_offset()` | 閴?| SDK function correctly called |
| `linear_pose_interpolation()` | 閴?| Has fallback implementation |
| Body yaw range | 閴?| Clamped to 鍗?60鎺?|

---

## 棣冩暋 v0.9.5 Updates (2026-01-19)

### Major Changes: Modular Architecture Refactoring

The codebase has been restructured into a modular architecture with 5 sub-packages:

| Package | Purpose | Key Modules |
|---------|---------|-------------|
| `core/` | Core infrastructure | `config.py`, `service_base.py`, `system_diagnostics.py` |
| `motion/` | Motion control | `antenna.py`, `pose_composer.py`, `command_runtime.py`, `control_runtime.py`, `idle_runtime.py`, `smoothing.py` |
| `vision/` | Vision processing | `frame_processor.py`, `face_tracking_interpolator.py` |
| `audio/` | Audio processing | `microphone.py`, `doa_tracker.py` |
| `entities/` | HA entity management | `entity_factory.py`, `entity_keys.py`, `event_emotion_mapper.py` |

### New Features

1. **Historical note**
   - Earlier versions explored direct sleep/wake callbacks and polling-based state handling
   - Current runtime no longer uses app-managed sleep/wake callbacks

2. **Camera runtime evolution**
   - Camera lifecycle was later split into dedicated runtime/processing/http helpers
   - Current runtime can fully stop camera service when `Idle Behavior` is disabled

### Audio Optimizations

| Parameter | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Audio chunk size | 1024 samples | 512 samples | 64ms 鈫?32ms latency with lower CPU load |
| Audio loop delay | 10ms | 1ms | Faster VAD response |
| Stereo閳墷ono | Mean of channels | First channel | Cleaner signal |

### Code Quality Improvements

- Removed all legacy/compatibility code
- Centralized configuration in nested dataclasses
- NaN/Inf cleaning in audio pipeline
- Rotation clamping in face tracking to prevent IK collisions
