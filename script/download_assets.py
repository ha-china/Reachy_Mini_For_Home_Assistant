#!/usr/bin/env python3
"""Download wake word models and sound files."""

import os
import urllib.request
from pathlib import Path


def download_file(url: str, dest: Path) -> None:
    """Download a file from URL to destination."""
    print(f"Downloading {url}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    print(f"Saved to {dest}")


def main():
    """Main function."""
    base_dir = Path(__file__).parent.parent
    wakewords_dir = base_dir / "wakewords"
    sounds_dir = base_dir / "sounds"

    print("Downloading wake word models...")

    # Download okay_nabu model (microWakeWord)
    download_file(
        "https://github.com/kahrendt/microWakeWord/releases/download/v2.0.0/okay_nabu.tflite",
        wakewords_dir / "okay_nabu.tflite",
    )

    # Download stop model (microWakeWord)
    download_file(
        "https://github.com/kahrendt/microWakeWord/releases/download/v2.0.0/stop.tflite",
        wakewords_dir / "stop.tflite",
    )

    print("\nDownloading sound files...")

    # Note: These are placeholder URLs. You may need to replace them with actual sound files
    # or provide your own sound files.

    print("\nSound files need to be provided manually.")
    print("Please add the following files to the 'sounds' directory:")
    print("  - wake_word_triggered.flac  (played when wake word is detected)")
    print("  - timer_finished.flac       (played when timer finishes)")
    print("\nYou can use any short audio file in FLAC or WAV format.")
    print("For now, creating placeholder files...")

    # Create empty placeholder files
    (sounds_dir / "wake_word_triggered.flac").touch()
    (sounds_dir / "timer_finished.flac").touch()

    print("\nDownload complete!")
    print("\nTo add more wake words, visit:")
    print("  - https://github.com/kahrendt/microWakeWord (microWakeWord models)")
    print("  - https://github.com/dscripka/openWakeWord (openWakeWord models)")
    print("  - https://github.com/fwartner/home-assistant-wakewords-collection (collection)")


if __name__ == "__main__":
    main()