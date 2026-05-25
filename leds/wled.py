"""WLED HTTP client."""

import logging

import requests

logger = logging.getLogger(__name__)


class WledClient:
    def __init__(self, host: str, port: int = 80, timeout: float = 0.1):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._failed = False

    def send(self, segments) -> bool:
        url = f"http://{self.host}:{self.port}/json/state"
        body = {
            "seg": [
                {
                    "col": [[seg.color_r, seg.color_g, seg.color_b]],
                    "bri": seg.bri,
                    "fx": seg.fx,
                    "sx": seg.sx,
                    "ix": seg.ix,
                }
                for seg in segments
            ]
        }
        try:
            resp = requests.post(url, json=body, timeout=self.timeout)
            resp.raise_for_status()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.HTTPError):
            if not self._failed:
                logger.warning("WLED send failed: %s", url)
                self._failed = True
            return False

        if self._failed:
            logger.info("WLED connection recovered: %s", url)
            self._failed = False
        return True
