"""Zeroconf/mDNS service discovery for Home Assistant."""

import asyncio
import logging
import socket
from typing import Optional

from zeroconf import IPVersion, ServiceInfo, Zeroconf

_LOGGER = logging.getLogger(__name__)


class HomeAssistantZeroconf:
    """Zeroconf service discovery for Home Assistant."""

    def __init__(self, port: int, name: str):
        """Initialize zeroconf discovery."""
        self.port = port
        self.name = name
        self._zeroconf: Optional[Zeroconf] = None
        self._service_info: Optional[ServiceInfo] = None

    async def register_server(self) -> None:
        """Register the server with zeroconf."""
        try:
            self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)

            # Get local IP address
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)

            # Create service info
            service_type = "_esphomelib._tcp.local."
            service_name = f"{self.name}._esphomelib._tcp.local."

            self._service_info = ServiceInfo(
                service_type,
                name=service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    "version": "1.0",
                    "platform": "ReachyMini",
                },
                server=f"{hostname}.local.",
            )

            await asyncio.get_event_loop().run_in_executor(
                None, self._zeroconf.register_service, self._service_info
            )

            _LOGGER.info(
                "Registered zeroconf service: %s at %s:%s",
                service_name,
                local_ip,
                self.port,
            )
        except Exception as e:
            _LOGGER.error("Failed to register zeroconf service: %s", e)

    async def unregister_server(self) -> None:
        """Unregister the server from zeroconf."""
        if self._zeroconf and self._service_info:
            await asyncio.get_event_loop().run_in_executor(
                None, self._zeroconf.unregister_service, self._service_info
            )
            self._zeroconf.close()
            _LOGGER.info("Unregistered zeroconf service")