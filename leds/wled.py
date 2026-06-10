"""WLED HTTP client."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)


class WledClient:
    def __init__(self, host: str, port: int = 80, timeout: float = 1.0,
                 effect_names: list[str] | None = None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._failed = False
        self._session = requests.Session()
        self._effects: dict[str, int] | None = None
        self._warned_fx: set[str] = set()
        if effect_names is not None:
            self._effects = {name.lower(): idx for idx, name in enumerate(effect_names)}

    def _resolve_effects(self) -> None:
        url = f"http://{self.host}:{self.port}/json"
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            self._effects = {name.lower(): idx for idx, name in enumerate(data["effects"])}
        except Exception as exc:
            logger.warning("WLED effect resolution failed: %s: %s", url, exc)
            self._effects = {}

    def _resolve_fx(self, fx: int | str) -> int:
        if isinstance(fx, int):
            return fx
        key = fx.lower()
        if key in self._effects:
            return self._effects[key]
        if key not in self._warned_fx:
            logger.warning("Unknown WLED effect name %r, falling back to fx=0 (Solid)", fx)
            self._warned_fx.add(key)
        return 0

    def send(self, segments) -> float | None:
        if self._effects is None:
            self._resolve_effects()
        url = f"http://{self.host}:{self.port}/json/state"
        body = {
            "seg": [
                {
                    "col": seg.col,
                    "bri": seg.bri,
                    "fx": self._resolve_fx(seg.fx),
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
            resp = self._session.post(url, json=body, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            if not self._failed:
                logger.warning("WLED send failed: %s: %s", url, exc)
                self._failed = True
            return None

        rtt_ms = (time.monotonic() - t0) * 1000.0
        if self._failed:
            logger.info("WLED connection recovered: %s", url)
            self._failed = False
        return rtt_ms

    def close(self):
        self._session.close()


class WledDispatcher:
    """Sends pad-keyed segment data to N WLED boxes concurrently.

    Each WLED box must be pre-configured with a single segment at index 0.

    Returns max RTT across successful sends — compensates for the
    slowest target to keep visual sync tight across all boxes.
    """

    def __init__(self, targets, port=80, timeout=1.0, effect_names=None):
        if not targets:
            raise ValueError("wled_targets must not be empty")
        self._clients = {}
        for entry in targets:
            pad = entry["pad"]
            host = entry["host"]
            entry_port = entry.get("port", port)
            self._clients[pad] = WledClient(host=host, port=entry_port, timeout=timeout,
                                            effect_names=effect_names)
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
            future = self._executor.submit(client.send, [seg])
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
            for client in self._clients.values():
                client.close()
            self._closed = True
