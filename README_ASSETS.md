# Assets Setup Guide

This document explains how to set up the required assets (wake word models and sound files).

## Included Assets

All required wake word models and sound files are already included in the repository:

### Wake Word Models (microWakeWord)

- `okay_nabu.tflite` - "Okay Nabu" (default)
- `stop.tflite` - "Stop"
- `alexa.tflite` - "Alexa"
- `hey_jarvis.tflite` - "Hey Jarvis"
- `hey_home_assistant.tflite` - "Hey Home Assistant"
- `hey_luna.tflite` - "Hey Luna"
- `hey_mycroft.tflite` - "Hey Mycroft"
- `okay_computer.tflite` - "Okay Computer"
- `choo_choo_homie.tflite` - "Choo Choo Homie"

### Wake Word Models (openWakeWord)

Located in `wakewords/openWakeWord/`:
- `alexa_v0.1.tflite` - Alexa
- `hey_jarvis_v0.1.tflite` - Hey Jarvis
- `hey_mycroft_v0.1.tflite` - Hey Mycroft
- `hey_rhasspy_v0.1.tflite` - Hey Rhasspy
- `ok_nabu_v0.1.tflite` - Okay Nabu

### Sound Files

- `wake_word_triggered.flac` - Played when wake word is detected
- `timer_finished.flac` - Played when timer finishes

## Wake Word Models

The application uses two wake word engines:
- **microWakeWord**: Lightweight, good for embedded systems
- **openWakeWord**: More accurate, uses more resources

### Adding Custom Wake Words

#### microWakeWord Models

1. Download a model from [microWakeWord releases](https://github.com/kahrendt/microWakeWord/releases)
2. Place the `.tflite` file in the `wakewords/` directory
3. Create a corresponding `.json` file:

```json
{
  "type": "microWakeWord",
  "wake_word": "Your Wake Word",
  "trained_languages": ["en"]
}
```

#### openWakeWord Models

1. Download a model from [home-assistant-wakewords-collection](https://github.com/fwartner/home-assistant-wakewords-collection)
2. Place the `.tflite` file in the `wakewords/` directory
3. Create a corresponding `.json` file:

```json
{
  "type": "openWakeWord",
  "wake_word": "Your Wake Word",
  "model": "your_wake_word.tflite",
  "trained_languages": ["en"]
}
```

### Popular Wake Words

Here are some popular wake words you can add:

- **Hey Jarvis**: [Download](https://github.com/fwartner/home-assistant-wakewords-collection/raw/main/en/hey_jarvis/hey_jarvis.tflite)
- **Alexa**: [Download](https://github.com/fwartner/home-assistant-wakewords-collection/raw/main/en/alexa/alexa.tflite)
- **Hey Google**: [Download](https://github.com/fwartner/home-assistant-wakewords-collection/raw/main/en/hey_google/hey_google.tflite)
- **GLaDOS**: [Download](https://github.com/fwartner/home-assistant-wakewords-collection/raw/main/en/glados/glados.tflite)

## Sound Files

The application uses sound files for feedback:

### Included Files

1. **wake_word_triggered.flac** - Played when wake word is detected
2. **timer_finished.flac** - Played when timer finishes

### Customizing Sound Files

You can replace these files with your own:

1. Keep them short (1-2 seconds)
2. Use FLAC or WAV format
3. Sample rate: 16kHz or 44.1kHz
4. Mono or stereo

### Example Using Online Tools

1. Go to [TTSMP3](https://ttsmp3.com/)
2. Enter text like "I'm listening" or "Timer finished"
3. Generate and download as MP3
4. Convert to FLAC using [Online Audio Converter](https://online-audio-converter.com/)
5. Replace the file in `sounds/` directory

## Directory Structure

After setup, your directory should look like:

```
reachy_mini_ha_voice/
├── wakewords/
│   ├── okay_nabu.json
│   ├── okay_nabu.tflite          # Downloaded
│   ├── stop.json
│   ├── stop.tflite               # Downloaded
│   ├── hey_jarvis.json           # Optional
│   └── hey_jarvis.tflite         # Optional
└── sounds/
    ├── wake_word_triggered.flac  # You provide
    └── timer_finished.flac       # You provide
```

## Troubleshooting

### Wake Word Not Detected

1. Check that the `.tflite` file exists
2. Verify the `.json` configuration is correct
3. Try a different wake word
4. Check microphone input volume

### Sound Not Playing

1. Verify the sound file exists and is not empty
2. Check audio output device is configured
3. Try playing the file manually: `aplay sounds/wake_word_triggered.flac`

### Model Loading Errors

1. Ensure the model is compatible with your architecture
2. Check that TensorFlow Lite is installed correctly
3. Verify the model file is not corrupted

## Additional Resources

- [microWakeWord GitHub](https://github.com/kahrendt/microWakeWord)
- [openWakeWord GitHub](https://github.com/dscripka/openWakeWord)
- [Home Assistant Wake Words Collection](https://github.com/fwartner/home-assistant-wakewords-collection)
- [ESPHome Voice Assistant](https://esphome.io/components/voice_assistant.html)