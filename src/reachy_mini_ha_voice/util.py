"""Utility functions."""

import logging
import socket


_LOGGER = logging.getLogger(__name__)


def get_mac() -> str:
    """Get the MAC address of the first network interface."""
    try:
        mac = ":".join(
            f"{byte:02x}" for byte in socket.gethostbyname(socket.gethostname()).encode()
        )
    except Exception:
        mac = "00:00:00:00:00:00"

    return mac