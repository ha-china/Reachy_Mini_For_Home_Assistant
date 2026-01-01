# Wake Word Models

This directory contains wake word models for the voice assistant.

## Supported Wake Word Engines

### microWakeWord
- Models: TensorFlow Lite (.tflite)
- Configuration: JSON file
- Source: https://github.com/kah0st/microWakeWord

### openWakeWord
- Models: TensorFlow Lite (.tflite)
- Configuration: JSON file
- Source: https://github.com/dscripka/openWakeWord

## How to Add Wake Word Models

### Option 1: Use Pre-trained Models

1. Download models from the official repositories:
   - microWakeWord: https://github.com/kah0st/microWakeWord/tree/main/models
   - openWakeWord: https://github.com/dscripka/openWakeWord/tree/main/models

2. Place the model files in this directory:
   ```
   wakewords/
   ├── okay_nabu.tflite
   ├── okay_nabu.json
   ├── hey_jarvis.tflite
   ├── hey_jarvis.json
   └── ...
   ```

### Option 2: Train Your Own Models

#### microWakeWord
```bash
# Install microWakeWord
pip install pymicro-wakeword

# Train your model
pymicro-wakeword train \
  --wake-word "Hey Reachy" \
  --training-data ./training_data \
  --output ./wakewords/hey_reachy.tflite
```

#### openWakeWord
```bash
# Install openWakeWord
pip install pyopen-wakeword

# Train your model
oww-train \
  --wake-word "Hey Reachy" \
  --training-data ./training_data \
  --output ./wakewords/hey_reachy.tflite
```

## Model Configuration Format

### microWakeWord JSON Format
```json
{
  "type": "micro",
  "wake_word": "Okay Nabu",
  "author": "Kevin Ahrendt",
  "website": "https://www.kevinahrendt.com/",
  "model": "okay_nabu.tflite",
  "trained_languages": ["en"],
  "version": 2,
  "micro": {
    "probability_cutoff": 0.97,
    "feature_step_size": 10,
    "sliding_window_size": 5,
    "tensor_arena_size": 22860,
    "minimum_esphome_version": "2024.7.0"
  }
}
```

### openWakeWord JSON Format
```json
{
  "type": "openWakeWord",
  "wake_word": "Alexa",
  "model": "alexa_v0.1.tflite"
}
```

## Default Wake Words

The following wake words are recommended for Reachy Mini:

1. **Okay Nabu** (microWakeWord) - Default
2. **Hey Reachy** (Custom) - Recommended for this project
3. **Hey Jarvis** (microWakeWord)
4. **Alexa** (openWakeWord)

## Downloading Pre-trained Models

### microWakeWord Models
```bash
# Download Okay Nabu
wget https://github.com/kah0st/microWakeWord/raw/main/models/okay_nabu.tflite -O wakewords/okay_nabu.tflite
wget https://github.com/kah0st/microWakeWord/raw/main/models/okay_nabu.json -O wakewords/okay_nabu.json

# Download Hey Jarvis
wget https://github.com/kah0st/microWakeWord/raw/main/models/hey_jarvis.tflite -O wakewords/hey_jarvis.tflite
wget https://github.com/kah0st/microWakeWord/raw/main/models/hey_jarvis.json -O wakewords/hey_jarvis.json
```

### openWakeWord Models
```bash
# Download Alexa
wget https://github.com/dscripka/openWakeWord/raw/main/models/alexa_v0.1.tflite -O wakewords/alexa.tflite

# Create config file
cat > wakewords/alexa.json << EOF
{
  "type": "openWakeWord",
  "wake_word": "Alexa",
  "model": "alexa.tflite"
}
EOF
```

## Notes

- Wake word models are binary files and cannot be included in the repository
- Users must download or train their own models
- Models should be placed in this directory
- Configuration files must match the model filenames