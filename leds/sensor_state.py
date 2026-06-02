"""Shared sensor state with thread-safe access."""

import threading

GSR_PAIRS = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]

# Node N receives GSR data for these global pair indices (FDM: every node has 3 slots).
NODE_GSR_MAPPING = [[0, 1, 2], [3, 4, 0], [5, 1, 3], [2, 4, 5]]


class SensorState:
    def __init__(self):
        self._lock = threading.Lock()
        self._cap = [0.0] * 4
        self._gsr_mag = [0.0] * 6

    def set_cap(self, pad_index: int, value: float) -> None:
        with self._lock:
            self._cap[pad_index] = value

    def set_gsr_mag(self, global_pair_index: int, mag: float) -> None:
        with self._lock:
            self._gsr_mag[global_pair_index] = mag

    def snapshot(self):
        with self._lock:
            return (list(self._cap), list(self._gsr_mag))
