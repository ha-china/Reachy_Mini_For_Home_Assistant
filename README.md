---
title: Reachy Mini Home Assistant Voice Assistant
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 5.33.0
app_file: app.py
pinned: false
tags:
  - reachy_mini
  - reachy_mini_python_app
---

# Reachy Mini Home Assistant Voice Assistant

A voice assistant application for **Reachy Mini robot** that integrates with Home Assistant via ESPHome protocol.

> **Note**: This is a Reachy Mini App, not a Hugging Face Space. Install it on your Reachy Mini robot.

## Features

- **Local Wake Word Detection**: Uses microWakeWord for offline wake word detection
- **ESPHome Integration**: Seamlessly connects to Home Assistant
- **Camera Streaming**: MJPEG video stream for Home Assistant Generic Camera integration
- **Motion Control**: Head movements and antenna animations during voice interaction
- **Zero Configuration**: Install and run - all settings are managed in Home Assistant
- **Full Robot Control**: Expose 30+ entities to Home Assistant for complete robot control
  - Motor control (enable/disable, mode selection)
  - Head position and orientation control
  - Body rotation control
  - Antenna animation control
  - Look-at target control
  - Audio sensors (DOA, speech detection)
  - System diagnostics and monitoring
  - IMU sensors (wireless version only)

## Requirements

- Reachy Mini robot (with reachy-mini SDK)
- Home Assistant with ESPHome integration
- Python 3.10+

## Installation

Install from Reachy Mini App Store or manually:

```bash
pip install reachy-mini-ha-voice
```

## Usage

The app runs automatically when installed on Reachy Mini. After installation:

1. Open Home Assistant
2. Go to **Settings** -> **Devices & Services** -> **Add Integration**
3. Search for **ESPHome**
4. Enter your Reachy Mini's IP address with port `6053`
5. The voice assistant will be automatically discovered

### Camera Setup

The camera stream is available at `http://<reachy-mini-ip>:8081/stream`. To add it to Home Assistant:

1. Go to **Settings** -> **Devices & Services** -> **Add Integration**
2. Search for **Generic Camera**
3. Enter the stream URL: `http://<reachy-mini-ip>:8081/stream`
4. Set content type to `image/jpeg`

You can also access:
- **Live Stream**: `http://<reachy-mini-ip>:8081/stream` - MJPEG video stream
- **Snapshot**: `http://<reachy-mini-ip>:8081/snapshot` - Single JPEG image
- **Status Page**: `http://<reachy-mini-ip>:8081/` - Web interface with stream preview

### Wake Words

Default wake word: **"Okay Nabu"**

Additional wake words can be configured through Home Assistant.

## ESPHome Entities

This application exposes 45+ entities to Home Assistant for complete robot control:

### Status & Control (Phase 1)
- **Daemon State** - Monitor robot daemon status
- **Backend Ready** - Check if backend is ready
- **Error Message** - View current error messages
- **Speaker Volume** - Control audio volume (0-100%)

### Motor Control (Phase 2)
- **Motors Enabled** - Enable/disable motor torque
- **Motor Mode** - Select motor mode (enabled/disabled/gravity_compensation)
- **Wake Up** - Execute wake up animation
- **Go to Sleep** - Execute sleep animation

### Pose Control (Phase 3)
- **Head Position** - Control X/Y/Z position (+/-50mm)
- **Head Orientation** - Control roll/pitch/yaw angles
- **Body Yaw** - Rotate body (+/-160 degrees)
- **Antennas** - Control left/right antenna angles (+/-90 degrees)

### Look At Control (Phase 4)
- **Look At X/Y/Z** - Point head at world coordinates

### Audio Sensors (Phase 5)
- **DOA Angle** - Direction of arrival angle
- **Speech Detected** - Real-time speech detection

### Diagnostics (Phase 6)
- **Control Loop Frequency** - Monitor control loop performance
- **SDK Version** - View SDK version
- **Robot Name** - Robot identifier
- **Wireless Version** - Check if wireless version
- **Simulation Mode** - Check if in simulation
- **WLAN IP** - Wireless network IP address

### IMU Sensors (Phase 7 - Wireless only)
- **Accelerometer** - X/Y/Z acceleration (m/s^2)
- **Gyroscope** - X/Y/Z angular velocity (rad/s)
- **Temperature** - IMU temperature (degrees Celsius)

### Emotion Control (Phase 8)
- **Emotion** - Select emotion (Happy/Sad/Angry/Fear/Surprise/Disgust)

### Audio Control (Phase 9)
- **Microphone Volume** - Control microphone input level (0-100%)

### Camera (Phase 10)
- **Camera** - ESPHome Camera entity with live preview in Home Assistant

### LED Control (Phase 11)
- **LED Brightness** - Control LED brightness (0-100%)
- **LED Effect** - Select LED effect (off/solid/breathing/rainbow/doa)
- **LED Color R/G/B** - Control LED color (0-255 per channel)

### Audio Processing (Phase 12)
- **AGC Enabled** - Toggle automatic gain control
- **AGC Max Gain** - Set maximum AGC gain (0-30 dB)
- **Noise Suppression** - Set noise suppression level (0-100%)
- **Echo Cancellation Converged** - Monitor echo cancellation status

## How It Works

```
[Reachy Mini Microphone] -> [Local Wake Word Detection] -> [ESPHome Protocol]
                                                                  |
                                                                  v
[Reachy Mini Speaker] <- [TTS Response] <- [Home Assistant STT/TTS]
        |
        v
[Head Motion & Antenna Animation]

[Reachy Mini Camera] -> [MJPEG Server :8081] -> [Home Assistant Generic Camera]
```

- **Wake word detection** runs locally on Reachy Mini
- **Speech-to-Text (STT)** and **Text-to-Speech (TTS)** are handled by Home Assistant
- **Motion feedback** provides visual response during voice interaction
- **Camera streaming** provides real-time video feed to Home Assistant

## Project Structure

```
reachy_mini_ha_voice/
|-- reachy_mini_ha_voice/
|   |-- __init__.py
|   |-- __main__.py          # CLI entry point
|   |-- main.py              # App entry point
|   |-- voice_assistant.py   # Voice assistant service
|   |-- camera_server.py     # MJPEG camera streaming server
|   |-- satellite.py         # ESPHome protocol handler
|   |-- audio_player.py      # Audio playback
|   |-- motion.py            # Motion control
|   |-- models.py            # Data models
|   |-- entity.py            # ESPHome base entities
|   |-- entity_extensions.py # Extended entity types
|   |-- reachy_controller.py # Reachy Mini controller wrapper
|   |-- api_server.py        # API server
|   |-- zeroconf.py          # mDNS discovery
|   |-- util.py              # Utilities
|   |-- wakewords/           # Wake word models (auto-downloaded)
|   |-- sounds/              # Sound effects (auto-downloaded)
|   |-- pyproject.toml
|   |-- README.md
|   +-- PROJECT_PLAN.md
```

## Dependencies

- `reachy-mini` - Reachy Mini SDK
- `aioesphomeapi` - ESPHome protocol
- `pymicro-wakeword` - Wake word detection
- `opencv-python` - Camera streaming
- `sounddevice` / `soundfile` - Audio processing
- `zeroconf` - mDNS discovery

## License

Apache 2.0 License

## Acknowledgments

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) - Original ESPHome voice assistant
- [Pollen Robotics](https://www.pollen-robotics.com/) - Reachy Mini robot
