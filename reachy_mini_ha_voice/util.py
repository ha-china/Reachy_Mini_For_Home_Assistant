"""Utility functions."""

import hashlib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Optional


def call_all(*funcs: Optional[Callable[[], None]]) -> None:
    """Call all non-None functions."""
    for func in funcs:
        if func is not None:
            func()


def get_mac() -> str:
    """Return a stable MAC address for device identification.

    Uses a cached device ID stored in a file to ensure the same ID
    is used across restarts, preventing Home Assistant from seeing
    the device as new each time.
    """
    # Store device ID in a persistent location
    local_dir = Path(__file__).parent.parent / "local"
    local_dir.mkdir(parents=True, exist_ok=True)
    device_id_file = local_dir / ".device_id"

    if device_id_file.exists():
        try:
            return device_id_file.read_text().strip()
        except Exception:
            pass

    # Generate a stable device ID based on machine UUID
    machine_id = uuid.getnode()
    # Create a hash to ensure consistent format
    device_id = hashlib.md5(str(machine_id).encode()).hexdigest()[:12]

    try:
        device_id_file.write_text(device_id)
    except Exception:
        pass

    return device_id
