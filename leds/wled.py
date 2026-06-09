"""WLED HTTP client."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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


class WledDispatcher:
    """Sends pad-keyed segment data to N WLED boxes concurrently.

    Each WLED box must be pre-configured with exactly 2 segments at
    indices 0 and 1. Both segments receive identical parameters.

    Returns max RTT across successful sends — compensates for the
    slowest target to keep visual sync tight across all boxes.
    """

    def __init__(self, targets, port=80, timeout=0.1):
        if not targets:
            raise ValueError("wled_targets must not be empty")
        self._clients = {}
        for entry in targets:
            pad = entry["pad"]
            host = entry["host"]
            entry_port = entry.get("port", port)
            self._clients[pad] = WledClient(host=host, port=entry_port, timeout=timeout)
        self._executor = ThreadPoolExecutor(max_workers=len(self._clients))
        self._closed = False

    @property
    def clients(self):
        return self._clients

    def send(self, pad_segments):
        futures = {}
        for pad, client in self._clients.items():
            seg = pad_segments.get(pad)
            if seg is None:
                continue
            future = self._executor.submit(client.send, [seg, seg])
            futures[future] = pad

        rtts = []
        for future in as_completed(futures):
            try:
                rtt = future.result()
            except Exception:
                logger.exception("Error sending to pad %s", futures[future])
                continue
            if rtt is not None:
                rtts.append(rtt)

        return max(rtts) if rtts else None

    def close(self):
        if not self._closed:
            self._executor.shutdown(wait=False)
            self._closed = True
