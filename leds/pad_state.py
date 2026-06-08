"""Per-pad state with thread-safe access."""

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class PadSnapshot:
    cap: float        # 0-1
    heartbeat: float  # Hz, 0 = none
    flux: float       # 0-1


class PadState:
    def __init__(self, pads: list[int]):
        self._lock = threading.Lock()
        self._pads = list(pads)
        self._index = {pad: i for i, pad in enumerate(pads)}
        self._cap = [0.0] * len(pads)
        self._heartbeat = [0.0] * len(pads)
        self._flux = [0.0] * len(pads)
        self._program = ""
        self._palette = ""
        self._bpm = 0.0
        self._sync_time = 0.0
        self._tempo_gen = 0

    def set_cap(self, pad: int, value: float) -> None:
        with self._lock:
            if pad not in self._index:
                return
            self._cap[self._index[pad]] = value

    def set_heartbeat(self, pad: int, value: float) -> None:
        with self._lock:
            if pad not in self._index:
                return
            self._heartbeat[self._index[pad]] = value

    def set_flux(self, pad: int, value: float) -> None:
        with self._lock:
            if pad not in self._index:
                return
            self._flux[self._index[pad]] = value

    def set_program(self, name: str) -> None:
        with self._lock:
            self._program = name

    def set_palette(self, name: str) -> None:
        with self._lock:
            self._palette = name

    def set_tempo(self, bpm: float, sync_time: float) -> None:
        with self._lock:
            self._bpm = bpm
            self._sync_time = sync_time
            self._tempo_gen += 1

    def snapshot(self) -> tuple:
        with self._lock:
            snapshots = [
                PadSnapshot(
                    cap=self._cap[i],
                    heartbeat=self._heartbeat[i],
                    flux=self._flux[i],
                )
                for i in range(len(self._pads))
            ]
            return (
                snapshots,
                self._program,
                self._palette,
                self._bpm,
                self._sync_time,
                self._tempo_gen,
            )
