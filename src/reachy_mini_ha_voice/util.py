"""Utility functions."""

import uuid
from collections.abc import Callable
from typing import Optional


def call_all(*funcs: Optional[Callable[[], None]]) -> None:
    """Call all non-None functions."""
    for func in funcs:
        if func is not None:
            func()


def get_mac() -> str:
    """Return MAC address formatted as hex with no colons."""
    return "".join(
        ["{:02x}".format((uuid.getnode() >> ele) & 0xFF) for ele in range(0, 8 * 6, 8)][
            ::-1
        ]
    )
