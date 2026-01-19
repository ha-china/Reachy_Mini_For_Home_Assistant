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
| Feature | Description |
|---------|-------------|
| Wake Word | Say "Okay Nabu" to activate (configurable) |
| Stop Word | Say "Stop" to end conversation |
| Continuous Mode | Keep talking without repeating wake word |
| STT/TTS | Uses Home Assistant's speech engines |

**Supported Wake Words:**
- Okay Nabu (default)
- Hey Jarvis
- Alexa
- Hey Luna

### Motion Control
| Feature | Description |
|---------|-------------|
| Head Control | Pitch, Roll, Yaw angles (±40°) |
| Body Rotation | Yaw angle (±160°) |
| Antenna Control | Left/Right angles (±90°) |
| Preset Actions | Nod, Shake, Look Around |

### Face Tracking
| Feature | Description |
|---------|-------------|
| Detection | YOLO-based face detection |
| Tracking | Head follows detected face |
| Body Following | Body rotates to follow head |
| Adaptive FPS | 15fps active, 2fps idle |

### Gesture Detection
| Gesture | Response |
|---------|----------|
| Thumbs Up 👍 | Happy animation |
| Thumbs Down 👎 | Sad animation |
| Wave 👋 | Wave back |
| OK Sign 👌 | Confirmation nod |
| Palm ✋ | Stop gesture |

### Emotion Responses
The robot automatically detects emotions from conversation and responds with:
- Head movements (nod, tilt, shake)
- Antenna animations
- 280+ emotion keywords recognized

### Audio Features
| Feature | Description |
|---------|-------------|
| Speaker Volume | 0-100% adjustable |
| AGC | Auto Gain Control (0-40dB) |
| Noise Suppression | 0-100% adjustable |
| Echo Cancellation | Built-in AEC |
| Sendspin | Multi-room audio support |

### Camera
| Feature | Description |
|---------|-------------|
| Live Stream | MJPEG stream for Home Assistant |
| Resolution | Configurable |
| Privacy | Local processing only, no cloud |

---

## Home Assistant Entities

### Controls (Read/Write)
| Entity | Type | Range |
|--------|------|-------|
| Speaker Volume | Number | 0-100% |
| Motors Enabled | Switch | On/Off |
| Motor Mode | Select | enabled/disabled/gravity |
| Face Tracking | Switch | On/Off |
| Gesture Detection | Switch | On/Off |
| DOA Tracking | Switch | On/Off |
| Continuous Conversation | Switch | On/Off |
| Head Pitch/Roll/Yaw | Number | ±40° |
| Body Yaw | Number | ±160° |
| Antenna Left/Right | Number | ±90° |
| AGC Max Gain | Number | 0-40dB |
| Noise Suppression | Number | 0-100% |

### Actions (Buttons)
| Button | Action |
|--------|--------|
| Wake Up | Wake robot from sleep |
| Go To Sleep | Put robot to sleep |
| Nod | Play nod animation |
| Shake | Play shake animation |
| Look Around | Play look around animation |

### Sensors (Read-Only)
| Sensor | Description |
|--------|-------------|
| Daemon State | Robot daemon status |
| Current Emotion | Detected emotion |
| Detected Gesture | Current hand gesture |
| DOA Angle | Sound source direction |
| Voice State | Voice assistant state |
| CPU/Memory/Disk | System diagnostics |

---

## Sleep Mode

### Enter Sleep
- Press "Go To Sleep" button in Home Assistant
- Robot relaxes motors, stops camera, pauses voice detection

### Wake Up
- Press "Wake Up" button in Home Assistant
- Or say the wake word
- Robot resumes all functions

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Not responding to wake word | Check AGC Max Gain, reduce background noise |
| Face tracking not working | Ensure adequate lighting, enable Face Tracking switch |
| No audio output | Check Speaker Volume, verify TTS engine in HA |
| Can't connect to HA | Verify same network, check port 6053 |
| Jerky movements | Check motor status, try Motor Power toggle |

---

## Quick Reference

```
Wake Word:     "Okay Nabu"
Stop Word:     "Stop"
Port:          6053 (ESPHome)
Camera Port:   8081 (MJPEG)
```

---

*Reachy Mini Voice Assistant v0.9.5*
