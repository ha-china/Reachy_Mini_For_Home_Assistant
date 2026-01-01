"""Hello World app for Reachy Mini."""

import logging
import threading
import time

from reachy_mini import ReachyMini, ReachyMiniApp

_LOGGER = logging.getLogger(__name__)


class HelloWorldApp(ReachyMiniApp):
    """Hello World App for Reachy Mini."""

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        """Run the Hello World app."""
        _LOGGER.info("Hello World App: Starting...")
        
        while not stop_event.is_set():
            _LOGGER.info("Hello World!")
            time.sleep(5)
        
        _LOGGER.info("Hello World App: Stopping...")