# Reachy Mini Voice Assistant - User Manual

## Requirements

### Hardware
- Reachy Mini robot (with ReSpeaker XVF3800 microphone)
- Network connection (WiFi or Ethernet)

### Software
- Home Assistant (2024.1 or later)
- ESPHome integration enabled in Home Assistant

---

## Installation

### Step 1: Install the App
Install `reachy_mini_ha_voice` from the Reachy Mini App Store.

### Step 2: Start the App
The app will automatically:
- Start the ESPHome server on port 6053
- Download required wake word models and sound files
- Register with mDNS for auto-discovery

### Step 3: Connect to Home Assistant
**Automatic (Recommended):**
Home Assistant will auto-discover Reachy Mini via mDNS.

**Manual:**
1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Select "ESPHome"
4. Enter the robot's IP address and port 6053

---

## Features

### Voice Assistant
- **Wake Word Detection**: Say "Okay Nabu" to activate (local processing)
- **Stop Word**: Say "Stop" to end conversation
- **Continuous Conversation Mode**: Keep talking without repeating wake word
- **STT/TTS**: Uses Home Assistant's configured speech engines

**Supported Wake Words:**
- Okay Nabu (default)
- Hey Jarvis
- Alexa
- Hey Luna

### Face Tracking
- YOLO-based face detection
- Head follows detected face
- Body follows head when turned far
- Adaptive frame rate: 15fps active, 2fps idle

### Gesture Detection
Detected gestures and robot responses:

| Gesture | Response |
|---------|----------|
| like (thumbs up) | Cheerful emotion |
| dislike (thumbs down) | Sad emotion |
| ok | Nod animation |
| peace | Enthusiastic emotion |
| stop | Stop speaking |
| call | Start listening |
| palm | Pause motion |
| fist | Rage emotion |
| one/two/three/four | Send HA event |

### Emotion Responses
The robot can play 35 different emotions:
- Basic: Happy, Sad, Angry, Fear, Surprise, Disgust
- Extended: Laughing, Loving, Proud, Grateful, Enthusiastic, Curious, Amazed, Shy, Confused, Thoughtful, Anxious, Scared, Frustrated, Irritated, Furious, Contempt, Bored, Tired, Exhausted, Lonely, Downcast, Resigned, Uncertain, Uncomfortable

### Audio Features
- Speaker volume control (0-100%)
- Microphone volume control (0-100%)
- AGC (Auto Gain Control, 0-40dB)
- Noise suppression (0-100%)
- Echo cancellation (built-in)

### DOA Sound Tracking
- Direction of Arrival detection
- Robot turns toward sound source on wake word
- Can be enabled/disabled via switch

---

## Home Assistant Entities

### Phase 1: Basic Status
| Entity | Type | Description |
|--------|------|-------------|
| Daemon State | Text Sensor | Robot daemon status |
| Backend Ready | Binary Sensor | Backend connection status |
| Speaker Volume | Number (0-100%) | Speaker volume control |

### Phase 2: Motor Control
| Entity | Type | Description |
|--------|------|-------------|
| Motors Enabled | Switch | Motor power on/off |
| Wake Up | Button | Wake robot from sleep |
| Go to Sleep | Button | Put robot to sleep |
| Sleep Mode | Binary Sensor | Current sleep state |
| Services Suspended | Binary Sensor | ML models unloaded state |

### Phase 3: Pose Control
| Entity | Type | Range |
|--------|------|-------|
| Head X/Y/Z | Number | ±50mm |
| Head Roll/Pitch/Yaw | Number | ±40° |
| Body Yaw | Number | ±160° |
| Antenna Left/Right | Number | ±90° |

### Phase 4: Look At Control
| Entity | Type | Description |
|--------|------|-------------|
| Look At X/Y/Z | Number | World coordinates for gaze target |

### Phase 5: DOA (Direction of Arrival)
| Entity | Type | Description |
|--------|------|-------------|
| DOA Angle | Sensor (°) | Sound source direction |
| Speech Detected | Binary Sensor | Voice activity detection |
| DOA Sound Tracking | Switch | Enable/disable DOA tracking |

### Phase 6: Diagnostics
| Entity | Type | Description |
|--------|------|-------------|
| Control Loop Frequency | Sensor (Hz) | Motion control loop rate |
| SDK Version | Text Sensor | Reachy Mini SDK version |
| Robot Name | Text Sensor | Device name |
| Wireless Version | Binary Sensor | Wireless model flag |
| Simulation Mode | Binary Sensor | Simulation flag |
| WLAN IP | Text Sensor | WiFi IP address |
| Error Message | Text Sensor | Current error |

### Phase 7: IMU Sensors (Wireless version only)
| Entity | Type | Description |
|--------|------|-------------|
| IMU Accel X/Y/Z | Sensor (m/s²) | Accelerometer |
| IMU Gyro X/Y/Z | Sensor (rad/s) | Gyroscope |
| IMU Temperature | Sensor (°C) | IMU temperature |

### Phase 8: Emotion Control
| Entity | Type | Description |
|--------|------|-------------|
| Emotion | Select | Choose emotion to play (35 options) |

### Phase 9: Audio Control
| Entity | Type | Description |
|--------|------|-------------|
| Microphone Volume | Number (0-100%) | Mic gain control |

### Phase 10: Camera
| Entity | Type | Description |
|--------|------|-------------|
| Camera | Camera | Live MJPEG stream |

### Phase 12: Audio Processing
| Entity | Type | Description |
|--------|------|-------------|
| AGC Enabled | Switch | Auto gain control on/off |
| AGC Max Gain | Number (0-40dB) | Maximum AGC gain |
| Noise Suppression | Number (0-100%) | Noise reduction level |
| Echo Cancellation Converged | Binary Sensor | AEC status |

### Phase 21: Conversation
| Entity | Type | Description |
|--------|------|-------------|
| Continuous Conversation | Switch | Multi-turn conversation mode |

### Phase 22: Gesture Detection
| Entity | Type | Description |
|--------|------|-------------|
| Gesture Detected | Text Sensor | Current gesture name |
| Gesture Confidence | Sensor (%) | Detection confidence |

### Phase 23: Face Detection
| Entity | Type | Description |
|--------|------|-------------|
| Face Detected | Binary Sensor | Face in view |

### Phase 24: System Diagnostics
| Entity | Type | Description |
|--------|------|-------------|
| CPU Percent | Sensor (%) | CPU usage |
| CPU Temperature | Sensor (°C) | CPU temperature |
| Memory Percent | Sensor (%) | RAM usage |
| Memory Used | Sensor (GB) | RAM used |
| Disk Percent | Sensor (%) | Disk usage |
| Disk Free | Sensor (GB) | Disk free space |
| Uptime | Sensor (hours) | System uptime |
| Process CPU | Sensor (%) | App CPU usage |
| Process Memory | Sensor (MB) | App memory usage |

---

## Sleep Mode

### Enter Sleep
- Press "Go to Sleep" button in Home Assistant
- Robot relaxes motors, stops camera, pauses voice detection

### Wake Up
- Press "Wake Up" button in Home Assistant
- Or say the wake word
- Robot resumes all functions

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Not responding to wake word | Increase AGC Max Gain, reduce background noise |
| Face tracking not working | Ensure adequate lighting, check Face Detected sensor |
| No audio output | Check Speaker Volume, verify TTS engine in HA |
| Can't connect to HA | Verify same network, check port 6053 |
| Gestures not detected | Ensure good lighting, face the camera directly |

---

## Quick Reference

```
Wake Word:     "Okay Nabu"
Stop Word:     "Stop"
ESPHome Port:  6053
Camera Port:   8081 (MJPEG)
```

---

*Reachy Mini Voice Assistant v0.9.5*
