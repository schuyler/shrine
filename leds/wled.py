"""WLED HTTP client."""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class WledClient:
    def __init__(self, host: str, port: int = 80, timeout: float = 0.1):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._failed = False

    def send(self, segments) -> float | None:
        url = f"http://{self.host}:{self.port}/json/state"
        body = {
            "seg": [
                {
                    "col": seg.col,
                    "bri": seg.bri,
                    "fx": seg.fx,
                    "sx": seg.sx,
                    "ix": seg.ix,
                    "pal": seg.pal,
                    "on": seg.on,
                }
                for seg in segments
            ]
        }
        t0 = time.monotonic()
        try:
            resp = requests.post(url, json=body, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException:
            if not self._failed:
                logger.warning("WLED send failed: %s", url)
                self._failed = True
            return None

        rtt_ms = (time.monotonic() - t0) * 1000.0
        if self._failed:
            logger.info("WLED connection recovered: %s", url)
            self._failed = False
        return rtt_ms
