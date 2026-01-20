"""Utility functions."""

import hashlib
import uuid
from collections.abc import Callable


def call_all(*funcs: Callable[[], None] | None) -> None:
    """Call all non-None functions."""
    for func in funcs:
        if func is not None:
            func()


def get_mac() -> str:
    """Return a stable MAC address for device identification.

    Uses the machine's hardware MAC address (via uuid.getnode()) which
    is stable across app reinstalls, preventing Home Assistant from
    seeing the device as new each time.
    """
    # uuid.getnode() returns the hardware MAC address as an integer
    # This is stable for the same machine regardless of app reinstalls
    machine_id = uuid.getnode()
    # Create a hash to ensure consistent 12-char hex format
    return hashlib.md5(str(machine_id).encode()).hexdigest()[:12]
