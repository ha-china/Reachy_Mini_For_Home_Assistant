"""
Quick start script - Opens the installation UI
"""

import sys
import subprocess


def main():
    """Main entry point"""
    print("Starting Reachy Mini Voice Assistant Installation UI...")
    print("Opening web interface at http://localhost:7860")
    print("Press Ctrl+C to stop\n")
    
    try:
        # Run the setup UI
        subprocess.run(
            [sys.executable, "setup_ui.py"],
            check=True
        )
    except KeyboardInterrupt:
        print("\n\nInstallation UI stopped.")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()