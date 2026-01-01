# Quick Start Guide

This guide will help you quickly set up the Reachy Mini Home Assistant Voice Assistant.

## Prerequisites

- Reachy Mini robot (connected and powered on)
- Home Assistant instance with ESPHome integration
- Python 3.8 or higher installed on Reachy Mini
- Network connection between Reachy Mini and Home Assistant

## Step 1: Install Dependencies

```bash
# SSH into your Reachy Mini
ssh reachy@<reachy-ip>

# Clone the repository
git clone https://github.com/yourusername/reachy_mini_ha_voice.git
cd reachy_mini_ha_voice

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

## Step 2: Download Wake Word Models

```bash
# Download Okay Nabu model (default)
cd wakewords
wget https://github.com/kah0st/microWakeWord/raw/main/models/okay_nabu.tflite -O okay_nabu.tflite
cp okay_nabu.json.example okay_nabu.json

# Optional: Download Hey Jarvis model
wget https://github.com/kah0st/microWakeWord/raw/main/models/hey_jarvis.tflite -O hey_jarvis.tflite
wget https://github.com/kah0st/microWakeWord/raw/main/models/hey_jarvis.json -O hey_jarvis.json

cd ..
```

## Step 3: Configure Audio Devices

```bash
# List available audio devices
python -m reachy_mini_ha_voice --list-input-devices
python -m reachy_mini_ha_voice --list-output-devices

# Note the device names you want to use
```

## Step 4: Create Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env file
nano .env
```

Add your configuration:

```env
# Audio Configuration
AUDIO_INPUT_DEVICE=Reachy Microphone
AUDIO_OUTPUT_DEVICE=Reachy Speaker
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

## Step 5: Start the Application

```bash
# Start the voice assistant
python -m reachy_mini_ha_voice

# Or with custom configuration
python -m reachy_mini_ha_voice \
  --name "My Reachy Mini" \
  --audio-input-device "Reachy Microphone" \
  --audio-output-device "Reachy Speaker" \
  --wake-model okay_nabu
```

## Step 6: Connect to Home Assistant

1. Open Home Assistant
2. Go to **Settings** → **Devices & Services**
3. Click **Add Integration**
4. Search for **ESPHome**
5. Click **Set up another instance of ESPHome**
6. Enter Reachy Mini's IP address and port (default: 6053)
7. Click **Submit**

## Step 7: Test

1. Say the wake word: **"Okay Nabu"**
2. Reachy Mini should nod to acknowledge
3. Speak your command
4. Reachy Mini should respond with motion and voice (if configured)

## Troubleshooting

### Wake Word Not Detected

- Check if the wake word model is downloaded: `ls wakewords/`
- Verify the model name in configuration matches the file
- Check microphone is working: `python -m reachy_mini_ha_voice --list-input-devices`
- Increase microphone volume if needed

### No Audio Output

- Check speaker is working: `python -m reachy_mini_ha_voice --list-output-devices`
- Verify audio output device name in configuration
- Check speaker volume

### Cannot Connect to Home Assistant

- Verify network connectivity: `ping <home-assistant-ip>`
- Check ESPHome port (6053) is not blocked by firewall
- Ensure Home Assistant ESPHome integration is installed
- Check Home Assistant logs for connection errors

### Motion Not Working

- Verify Reachy Mini is connected: Check if robot responds to basic commands
- Check robot host in configuration
- Ensure Reachy Mini SDK is installed: `pip show reachy-mini`
- Check robot is not in sleep mode

## Advanced Configuration

### Custom Wake Word

1. Train your own wake word model (see wakewords/README.md)
2. Place the model files in wakewords/ directory
3. Update configuration to use your model

### Multiple Wake Words

```bash
# Add additional wake word models to wakewords/ directory
# Update configuration to enable multiple wake words
```

### Web UI

```bash
# Start with Gradio web interface
python -m reachy_mini_ha_voice --gradio

# Access at http://<reachy-ip>:7860
```

### Wireless Reachy Mini

```bash
# For wireless version
python -m reachy_mini_ha_voice --wireless
```

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Check [ARCHITECTURE.md](ARCHITECTURE.md) for system architecture
- See [REQUIREMENTS.md](REQUIREMENTS.md) for detailed requirements
- Explore [profiles/](profiles/) for personality customization

## Support

- GitHub Issues: https://github.com/yourusername/reachy_mini_ha_voice/issues
- Documentation: https://github.com/yourusername/reachy_mini_ha_voice#readme
- Community: Join our Discord server

---

**Happy talking with your Reachy Mini!** 🤖