#!/usr/bin/env python3
"""Main entry point - for Hugging Face Spaces display only.

This application is designed to run on Reachy Mini robots.
To use it, install the app on your Reachy Mini from the dashboard.

For standalone usage, this would require command-line arguments:
  python -m reachy_mini_ha_voice --name "ReachyMini"
"""

import sys

if __name__ == "__main__":
    print("Reachy Mini Home Assistant Voice Assistant")
    print("=" * 50)
    print()
    print("This application is designed to run on Reachy Mini robots.")
    print()
    print("To use it:")
    print("1. Install this app on your Reachy Mini from the dashboard")
    print("2. Enable the app in the Reachy Mini applications section")
    print("3. The ESPHome voice assistant will start on port 6053")
    print("4. Home Assistant will auto-discover the device")
    print()
    print("For more information, see:")
    print("https://huggingface.co/spaces/djhui5710/reachy_mini_ha_voice")
    print()
    sys.exit(0)