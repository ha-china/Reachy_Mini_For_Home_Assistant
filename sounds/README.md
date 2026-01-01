# Sound Effects

This directory contains sound effects for the voice assistant.

## Sound Effects

### Required Sounds

1. **Wake Word Triggered** - Played when wake word is detected
   - Filename: `wake_word_triggered.flac` or `wake_word_triggered.mp3`
   - Duration: ~0.5 seconds
   - Description: A short beep or chime to indicate wake word detection

2. **Timer Finished** - Played when a timer completes
   - Filename: `timer_finished.flac` or `timer_finished.mp3`
   - Duration: ~1 second
   - Description: A notification sound for timer completion

### Optional Sounds

1. **Listening Started** - Played when the assistant starts listening
   - Filename: `listening_started.flac` or `listening_started.mp3`
   - Duration: ~0.3 seconds

2. **Processing** - Played while processing voice input
   - Filename: `processing.flac` or `processing.mp3`
   - Duration: ~0.5 seconds (loopable)

3. **Error** - Played when an error occurs
   - Filename: `error.flac` or `error.mp3`
   - Duration: ~0.5 seconds

## How to Add Sounds

### Option 1: Use Pre-made Sounds

Download free sound effects from:
- Freesound: https://freesound.org/
- Zapsplat: https://www.zapsplat.com/
- Pixabay: https://pixabay.com/sound-effects/

### Option 2: Create Your Own Sounds

#### Using Audacity
1. Download and install Audacity: https://www.audacityteam.org/
2. Record or create your sound effect
3. Export as FLAC or MP3
4. Place in this directory

#### Using Python
```python
import numpy as np
from scipy.io import wavfile

# Create a simple beep
sample_rate = 16000
duration = 0.5
frequency = 440  # A4 note

t = np.linspace(0, duration, int(sample_rate * duration), False)
audio = np.sin(2 * np.pi * frequency * t) * 0.5  # 50% volume

# Save as WAV
wavfile.write('wake_word_triggered.wav', sample_rate, audio.astype(np.float32))
```

## Sound Format Requirements

- **Format**: FLAC, MP3, or WAV
- **Sample Rate**: 16kHz (recommended)
- **Channels**: Mono
- **Bit Depth**: 16-bit or higher
- **Duration**: < 2 seconds (for UI sounds)

## Default Sounds

If you don't have custom sounds, the application will use:
- System beep (if available)
- No sound (silent mode)

## Notes

- Sound files are binary files and cannot be included in the repository
- Users must provide their own sound effects
- Sounds should be short and non-intrusive
- Use royalty-free sounds to avoid copyright issues