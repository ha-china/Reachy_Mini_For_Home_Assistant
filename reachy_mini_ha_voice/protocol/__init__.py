"""Protocol layer for Reachy Mini HA Voice.

This package contains communication protocol implementations:
- ESPHome Native API (satellite)
- mDNS/Zeroconf discovery
- HTTP API server
"""

from .api_server import APIServer
from .satellite import VoiceSatelliteProtocol
from .zeroconf import HomeAssistantZeroconf

__all__ = [
    "APIServer",
    "HomeAssistantZeroconf",
    "VoiceSatelliteProtocol",
]
