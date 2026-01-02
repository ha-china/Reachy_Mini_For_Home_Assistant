---
title: Reachy Mini HA Voice
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "5.9.1"
app_file: app.py
pinned: false
---

# Reachy Mini Home Assistant Voice Assistant

A voice assistant application for **Reachy Mini robot** that integrates with Home Assistant via ESPHome protocol.

> **Note**: This is a Reachy Mini App, not a Hugging Face Space. Install it on your Reachy Mini robot.

## Features

- **Local Wake Word Detection**: Uses microWakeWord for offline wake word detection
- **ESPHome Integration**: Seamlessly connects to Home Assistant
- **Motion Control**: Head movements and antenna animations during voice interaction
- **Zero Configuration**: Install and run - all settings are managed in Home Assistant
- **Full Robot Control**: Expose 17+ entities to Home Assistant for complete robot control
  - Motor control (enable/disable, mode selection)
  - Head position and orientation control
  - Body rotation control
  - Antenna animation control
  - System status monitoring

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

### Wake Words

Default wake word: **"Okay Nabu"**

Additional wake words can be configured through Home Assistant.

## ESPHome Entities

This application exposes 17+ entities to Home Assistant for complete robot control:

### Status & Control
- **Daemon State** - Monitor robot daemon status
- **Backend Ready** - Check if backend is ready
- **Error Message** - View current error messages
- **Speaker Volume** - Control audio volume (0-100%)

### Motor Control
- **Motors Enabled** - Enable/disable motor torque
- **Motor Mode** - Select motor mode (enabled/disabled/gravity_compensation)
- **Wake Up** - Execute wake up animation
- **Go to Sleep** - Execute sleep animation

### Pose Control
- **Head Position** - Control X/Y/Z position (±50mm)
- **Head Orientation** - Control roll/pitch/yaw angles
- **Body Yaw** - Rotate body (±160°)
- **Antennas** - Control left/right antenna angles (±90°)

📖 **[View Complete Entity Documentation](ENTITIES.md)** - Includes usage examples, automations, and Lovelace dashboard configurations

## How It Works

```
[Reachy Mini Microphone] -> [Local Wake Word Detection] -> [ESPHome Protocol]
                                                                  |
                                                                  v
[Reachy Mini Speaker] <- [TTS Response] <- [Home Assistant STT/TTS]
        |
        v
[Head Motion & Antenna Animation]
```

- **Wake word detection** runs locally on Reachy Mini
- **Speech-to-Text (STT)** and **Text-to-Speech (TTS)** are handled by Home Assistant
- **Motion feedback** provides visual response during voice interaction

## Project Structure

```
reachy_mini_ha_voice/
├── reachy_mini_ha_voice/
│   ├── __init__.py
│   ├── main.py              # App entry point
│   ├── voice_assistant.py   # Voice assistant service
│   ├── satellite.py         # ESPHome protocol handler
│   ├── audio_player.py      # Audio playback
│   ├── motion.py            # Motion control
│   ├── models.py            # Data models
│   ├── entity.py            # ESPHome entities
│   ├── api_server.py        # API server
│   ├── zeroconf.py          # mDNS discovery
│   └── util.py              # Utilities
├── wakewords/               # Wake word models (auto-downloaded)
├── sounds/                  # Sound effects (auto-downloaded)
├── pyproject.toml
├── README.md
└── PROJECT_PLAN.md
```

## Dependencies

- `reachy-mini` - Reachy Mini SDK
- `aioesphomeapi` - ESPHome protocol
- `pymicro-wakeword` - Wake word detection
- `sounddevice` / `soundfile` - Audio processing
- `zeroconf` - mDNS discovery

## License

Apache 2.0 License

## Acknowledgments

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) - Original ESPHome voice assistant
- [Pollen Robotics](https://www.pollen-robotics.com/) - Reachy Mini robot
