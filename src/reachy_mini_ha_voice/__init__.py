"""
Reachy Mini Home Assistant Voice Assistant

A voice assistant application that runs on Reachy Mini robot and integrates
with Home Assistant via the ESPHome protocol.
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

# Check for required models on import
import os
import sys
import subprocess
from pathlib import Path

def download_file(url, dest_path):
    """Download a file from URL"""
    try:
        import urllib.request
        urllib.request.urlretrieve(url, dest_path)
        return True
    except Exception as e:
        print(f"  Error downloading {url}: {e}")
        return False

def check_and_download_files():
    """Check if required model files exist and download if missing"""
    wakewords_dir = Path(__file__).parent.parent.parent / "wakewords"
    sounds_dir = Path(__file__).parent.parent.parent / "sounds"
    
    # Ensure directories exist
    wakewords_dir.mkdir(parents=True, exist_ok=True)
    sounds_dir.mkdir(parents=True, exist_ok=True)
    
    missing_files = []
    downloaded_files = []
    
    # Check and download wake word models
    model_urls = {
        "okay_nabu.tflite": "https://github.com/esphome/micro-wake-word-models/raw/main/models/okay_nabu.tflite",
        "okay_nabu.json": "https://github.com/esphome/micro-wake-word-models/raw/main/models/okay_nabu.json",
        "hey_jarvis.tflite": "https://github.com/esphome/micro-wake-word-models/raw/main/models/hey_jarvis.tflite",
        "hey_jarvis.json": "https://github.com/esphome/micro-wake-word-models/raw/main/models/hey_jarvis.json",
    }
    
    for filename, url in model_urls.items():
        dest_path = wakewords_dir / filename
        if not dest_path.exists():
            missing_files.append(filename)
            print(f"Downloading {filename}...")
            if download_file(url, dest_path):
                downloaded_files.append(filename)
                print(f"  ✓ {filename} downloaded")
            else:
                print(f"  ✗ Failed to download {filename}")
    
    # Check and download sound effects
    sound_urls = {
        "wake_word_triggered.flac": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/wake_word_triggered.flac",
        "timer_finished.flac": "https://github.com/OHF-Voice/linux-voice-assistant/raw/main/sounds/timer_finished.flac",
    }
    
    for filename, url in sound_urls.items():
        dest_path = sounds_dir / filename
        if not dest_path.exists():
            missing_files.append(filename)
            print(f"Downloading {filename}...")
            if download_file(url, dest_path):
                downloaded_files.append(filename)
                print(f"  ✓ {filename} downloaded")
            else:
                print(f"  ✗ Failed to download {filename}")
    
    if downloaded_files:
        print(f"\n✓ Downloaded {len(downloaded_files)} file(s)")
    
    if missing_files:
        print(f"\n✗ Still missing {len(missing_files)} file(s):")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print("\n✓ All required files are present")
    return True

# Check and download files on import
check_and_download_files()

from .app import ReachyMiniVoiceApp
from .state import ServerState

__all__ = [
    "ReachyMiniVoiceApp",
    "ServerState",
    "__version__",
]