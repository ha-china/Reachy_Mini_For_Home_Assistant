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
from pathlib import Path

def check_required_files():
    """Check if required model files exist"""
    wakewords_dir = Path(__file__).parent.parent.parent / "wakewords"
    sounds_dir = Path(__file__).parent.parent.parent / "sounds"
    
    missing_files = []
    
    # Check wake word models
    required_models = [
        wakewords_dir / "okay_nabu.tflite",
        wakewords_dir / "okay_nabu.json",
    ]
    
    for model_file in required_models:
        if not model_file.exists():
            missing_files.append(model_file.name)
    
    # Check sound effects
    required_sounds = [
        sounds_dir / "wake_word_triggered.flac",
        sounds_dir / "timer_finished.flac",
    ]
    
    for sound_file in required_sounds:
        if not sound_file.exists():
            missing_files.append(sound_file.name)
    
    if missing_files:
        print("\n" + "="*60)
        print("WARNING: Required files are missing!")
        print("="*60)
        print("\nMissing files:")
        for file in missing_files:
            print(f"  - {file}")
        
        print("\nPlease run the download script:")
        print("  Linux/Mac: ./download_models.sh")
        print("  Windows: powershell -ExecutionPolicy Bypass -File download_models.ps1")
        print("\nOr run the automated installation script:")
        print("  Linux/Mac: ./install.sh")
        print("  Windows: powershell -ExecutionPolicy Bypass -File install.ps1")
        print("="*60 + "\n")
        return False
    
    return True

# Check on import
check_required_files()

from .app import ReachyMiniVoiceApp
from .state import ServerState

__all__ = [
    "ReachyMiniVoiceApp",
    "ServerState",
    "__version__",
]