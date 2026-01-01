---
title: Reachy Mini Home Assistant Voice Assistant
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: static
pinned: false
---

# Reachy Mini Home Assistant Voice Assistant

A voice assistant application that runs on **Reachy Mini robot** and integrates with Home Assistant via the ESPHome protocol.

> **Note**: This application runs directly on the Reachy Mini robot (Raspberry Pi 4), not on Hugging Face Spaces. The Hugging Face Space is used for code hosting and documentation only.

## Features

- 🎤 **Offline Wake Word Detection**: Uses microWakeWord or openWakeWord for local wake word detection
- 🔄 **ESPHome Integration**: Seamlessly integrates with Home Assistant through ESPHome protocol
- 🤖 **Motion Control**: Full control over Reachy Mini's head movements and antenna animations
- ⚡ **Low Latency**: Optimized for real-time voice interaction
- 🎭 **Expressive**: Speech-reactive motions and gestures

## Architecture

This project is based on [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) and adapted for Reachy Mini robot.

**Key Design**:
- STT (Speech-to-Text) and TTS (Text-to-Speech) are handled by Home Assistant
- Audio streams are transmitted via ESPHome protocol
- Wake word detection is processed locally on the robot
- Motion control enhances the voice interaction experience

## Installation

### Prerequisites

- Python 3.8 or higher
- Reachy Mini robot
- Home Assistant with ESPHome integration

### One-Click Installation (Recommended - No Commands Required!)

**Option 1: Web UI (Easiest)**
```bash
# Clone the repository
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# Run the installation UI
python start.py
```

Then open your browser to `http://localhost:7860` and click the **"🚀 Start Installation"** button!

The installation will automatically:
- ✓ Check Python version
- ✓ Create virtual environment
- ✓ Install all dependencies
- ✓ Download wake word models and sound effects
- ✓ Create configuration file
- ✓ Check Reachy Mini SDK installation
- ✓ Check audio devices

**Option 2: Command Line**
```bash
# Clone the repository
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# Run the automated installation script
# For Linux/Mac:
./install.sh

# For Windows:
powershell -ExecutionPolicy Bypass -File install.ps1
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Download wake word models and sound effects
# For Linux/Mac:
./download_models.sh

# For Windows:
powershell -ExecutionPolicy Bypass -File download_models.ps1

# Copy environment template
cp .env.example .env

# Configure your settings
# Edit .env file with your preferences
```

## Usage

### Basic Usage

```bash
# Start the voice assistant
python -m reachy_mini_ha_voice

# With custom configuration
python -m reachy_mini_ha_voice \
  --name "My Reachy Mini" \
  --audio-input-device "Microphone Name" \
  --audio-output-device "Speaker Name" \
  --wake-model okay_nabu
```

### List Audio Devices

```bash
# List available input devices
python -m reachy_mini_ha_voice --list-input-devices

# List available output devices
python -m reachy_mini_ha_voice --list-output-devices
```

### Web UI

```bash
# Start with Gradio web interface
python -m reachy_mini_ha_voice --gradio
```

### Wireless Version

```bash
# For wireless Reachy Mini
python -m reachy_mini_ha_voice --wireless
```

## Configuration

### Environment Variables

Create a `.env` file (copy from `.env.example`):

```env
# Audio Configuration
AUDIO_INPUT_DEVICE=
AUDIO_OUTPUT_DEVICE=
AUDIO_SAMPLE_RATE=16000
AUDIO_CHANNELS=1
AUDIO_BLOCK_SIZE=1024

# Voice Configuration
WAKE_WORD=okay_nabu
WAKE_WORD_DIR=wakewords

# Motion Configuration
MOTION_ENABLED=true
SPEECH_REACTIVE=true

# ESPHome Configuration
ESPHOME_HOST=0.0.0.0
ESPHOME_PORT=6053
ESPHOME_NAME=Reachy Mini

# Robot Configuration
ROBOT_HOST=localhost
ROBOT_WIRELESS=false

# Logging
LOG_LEVEL=INFO
```

### Configuration File

You can also use a `config.json` file:

```json
{
  "audio": {
    "input_device": null,
    "output_device": null,
    "sample_rate": 16000,
    "channels": 1,
    "block_size": 1024
  },
  "voice": {
    "wake_word": "okay_nabu",
    "wake_word_dirs": ["wakewords"]
  },
  "motion": {
    "enabled": true,
    "speech_reactive": true
  },
  "esphome": {
    "host": "0.0.0.0",
    "port": 6053,
    "name": "Reachy Mini"
  },
  "robot": {
    "host": "localhost",
    "wireless": false
  }
}
```

## Home Assistant Integration

### Step 1: Add ESPHome Integration

1. Go to Home Assistant → Settings → Devices & Services
2. Click "Add Integration"
3. Search for "ESPHome"
4. Click "Set up another instance of ESPHome"
5. Enter your Reachy Mini's IP address and port (default: 6053)
6. Click "Submit"

### Step 2: Configure Voice Assistant

Home Assistant should automatically detect the voice assistant. You can then:

- Set up voice commands
- Create automations
- Configure STT/TTS services

### Step 3: Test

1. Say the wake word (default: "Okay Nabu")
2. Speak your command
3. Reachy Mini should respond with motion and voice

## Project Structure

```
reachy_mini_ha_voice/
├── src/
│   └── reachy_mini_ha_voice/
│       ├── __init__.py
│       ├── main.py              # Entry point
│       ├── app.py               # Main application
│       ├── state.py             # State management
│       ├── audio/               # Audio processing
│       │   ├── adapter.py       # Audio device adapter
│       │   └── processor.py     # Audio processor
│       ├── voice/               # Voice processing
│       │   ├── detector.py      # Wake word detection
│       │   ├── stt.py           # STT (backup)
│       │   └── tts.py           # TTS (backup)
│       ├── motion/              # Motion control
│       │   ├── controller.py    # Motion controller
│       │   └── queue.py         # Motion queue
│       ├── esphome/             # ESPHome protocol
│       │   ├── protocol.py      # Protocol definitions
│       │   └── server.py        # ESPHome server
│       └── config/              # Configuration
│           └── manager.py        # Config manager
├── profiles/                    # Personality profiles
│   └── default/
├── wakewords/                   # Wake word models
├── pyproject.toml               # Project config
├── PROJECT_PLAN.md              # Project plan
├── ARCHITECTURE.md              # Architecture docs
├── REQUIREMENTS.md              # Requirements
└── README.md                    # This file
```

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e .[dev]

# Run tests
pytest

# Run with coverage
pytest --cov=reachy_mini_ha_voice
```

### Code Style

```bash
# Format code
ruff format .

# Lint code
ruff check .
```

## Documentation

- [Project Plan](PROJECT_PLAN.md) - Detailed project plan
- [Architecture](ARCHITECTURE.md) - System architecture and design
- [Requirements](REQUIREMENTS.md) - Functional and technical requirements

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Acknowledgments

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) - Original project
- [Pollen Robotics](https://www.pollen-robotics.com/) - Reachy Mini robot
- [Hugging Face](https://huggingface.co/) - Platform and tools

## Support

For issues and questions:
- Open an issue on GitHub
- Join the Discord community
- Check the documentation

---

Made with ❤️ for Reachy Mini and Home Assistant community