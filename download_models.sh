#!/bin/bash
# Script to download wake word models and sound effects

echo "Downloading wake word models and sound effects..."

# Create directories if they don't exist
mkdir -p wakewords
mkdir -p sounds

# Download wake word models
echo "Downloading okay_nabu model..."
wget https://github.com/esphome/micro-wake-word-models/raw/main/models/okay_nabu.json -O wakewords/okay_nabu.json
wget https://github.com/esphome/micro-wake-word-models/raw/main/models/okay_nabu.tflite -O wakewords/okay_nabu.tflite

echo "Downloading hey_jarvis model..."
wget https://github.com/esphome/micro-wake-word-models/raw/main/models/hey_jarvis.json -O wakewords/hey_jarvis.json
wget https://github.com/esphome/micro-wake-word-models/raw/main/models/hey_jarvis.tflite -O wakewords/hey_jarvis.tflite

# Download sound effects
echo "Downloading sound effects..."
wget https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/wake_word_triggered.flac -O sounds/wake_word_triggered.flac
wget https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/timer_finished.flac -O sounds/timer_finished.flac

echo "Download complete!"
echo ""
echo "Files downloaded:"
ls -lh wakewords/*.tflite wakewords/*.json sounds/*.flac