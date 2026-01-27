"""Utility functions."""

import os
from collections.abc import Callable


def call_all(*funcs: Callable[[], None] | None) -> None:
    """Call all non-None functions."""
    for func in funcs:
        if func is not None:
            func()


def get_mac() -> str:
    """Return the machine ID as device ID.
    
    Reads /etc/machine-id and returns first 12 characters.
    """
    machine_id = "00000000000000000000000000000000"
    try:
        with open("/etc/machine-id") as f:
            machine_id = f.read().strip()
    except Exception:
        pass
    
    # Return first 12 characters
    return machine_id[:12]
