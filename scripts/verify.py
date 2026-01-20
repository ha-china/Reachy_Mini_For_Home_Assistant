#!/usr/bin/env python3
"""Quick verification script to run before releasing.

Usage: python scripts/verify.py
"""

import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    errors = []

    # 1. Check imports work
    print("Checking imports...")
    try:
        from reachy_mini_ha_voice import __version__
        print(f"  ✓ Version: {__version__}")
    except Exception as e:
        errors.append(f"Import failed: {e}")

    # 2. Check device ID generation
    print("Checking device ID...")
    try:
        from reachy_mini_ha_voice.core.util import get_mac
        device_id = get_mac()
        print(f"  ✓ Device ID: {device_id}")

        # Verify it's stable (call twice)
        device_id2 = get_mac()
        if device_id != device_id2:
            errors.append(f"Device ID not stable: {device_id} != {device_id2}")
        else:
            print("  ✓ Device ID is stable")
    except Exception as e:
        errors.append(f"Device ID check failed: {e}")

    # 3. Check config loads
    print("Checking config...")
    try:
        from reachy_mini_ha_voice.core.config import Config
        print(f"  ✓ ESPHome device name: {Config.esphome.device_name}")
        print(f"  ✓ Camera port: {Config.camera.port}")
    except Exception as e:
        errors.append(f"Config check failed: {e}")

    # 4. Check animation file exists
    print("Checking animation file...")
    try:
        from reachy_mini_ha_voice.motion.animation_player import _ANIMATIONS_FILE
        if _ANIMATIONS_FILE.exists():
            print(f"  ✓ Animation file: {_ANIMATIONS_FILE}")
        else:
            errors.append(f"Animation file not found: {_ANIMATIONS_FILE}")
    except Exception as e:
        errors.append(f"Animation file check failed: {e}")

    # 5. Check wake word files
    print("Checking wake word files...")
    try:
        pkg_dir = Path(__file__).parent.parent / "reachy_mini_ha_voice"
        wakewords_dir = pkg_dir / "wakewords"
        required = ["okay_nabu.tflite", "okay_nabu.json", "stop.tflite", "stop.json"]
        for f in required:
            if (wakewords_dir / f).exists():
                print(f"  ✓ {f}")
            else:
                errors.append(f"Missing wake word file: {f}")
    except Exception as e:
        errors.append(f"Wake word check failed: {e}")

    # Summary
    print()
    if errors:
        print("=" * 50)
        print("ERRORS FOUND:")
        for err in errors:
            print(f"  ✗ {err}")
        print("=" * 50)
        return 1
    else:
        print("=" * 50)
        print("All checks passed! ✓")
        print("=" * 50)
        return 0


if __name__ == "__main__":
    sys.exit(main())
