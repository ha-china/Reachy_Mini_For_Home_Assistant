"""Utility functions."""

import hashlib
import logging
import uuid
from collections.abc import Callable
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


def call_all(*funcs: Callable[[], None] | None) -> None:
    """Call all non-None functions."""
    for func in funcs:
        if func is not None:
            func()


def get_mac() -> str:
    """Return a stable MAC address for device identification.

    Uses a cached device ID stored in a persistent location outside the
    package installation directory to ensure the same ID is used across
    app reinstalls, preventing Home Assistant from seeing the device as new.
    """
    # Use a persistent location that survives app reinstalls
    # Priority: /var/lib/reachy_mini_ha_voice > ~/.config/reachy_mini_ha_voice > package local
    persistent_dirs = [
        Path("/var/lib/reachy_mini_ha_voice"),  # System-level persistent storage
        Path.home() / ".config" / "reachy_mini_ha_voice",  # User-level config
        Path(__file__).parent.parent / "local",  # Fallback: package directory (not ideal)
    ]

    device_id_filename = ".device_id"
    device_id: str | None = None

    # Try to read existing device ID from any persistent location
    for persistent_dir in persistent_dirs:
        device_id_file = persistent_dir / device_id_filename
        if device_id_file.exists():
            try:
                device_id = device_id_file.read_text().strip()
                if device_id:
                    _LOGGER.debug(f"Loaded device ID from {device_id_file}")
                    break
            except Exception:
                pass

    # Generate new device ID if not found
    if not device_id:
        machine_id = uuid.getnode()
        device_id = hashlib.md5(str(machine_id).encode()).hexdigest()[:12]
        _LOGGER.info(f"Generated new device ID: {device_id}")

    # Save device ID to the most preferred writable location
    for persistent_dir in persistent_dirs:
        try:
            persistent_dir.mkdir(parents=True, exist_ok=True)
            device_id_file = persistent_dir / device_id_filename
            device_id_file.write_text(device_id)
            _LOGGER.debug(f"Saved device ID to {device_id_file}")
            break
        except PermissionError:
            continue
        except Exception as e:
            _LOGGER.debug(f"Could not save device ID to {persistent_dir}: {e}")
            continue

    return device_id
