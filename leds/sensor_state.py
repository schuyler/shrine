"""Shared sensor state with thread-safe access."""

import threading

GSR_PAIRS = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]

# Node N receives GSR data for these global pair indices.
# Node 0: no GSR RX; Node 1: pair 0; Node 2: pairs 1,3; Node 3: pairs 2,4,5
NODE_GSR_MAPPING = [[], [0], [1, 3], [2, 4, 5]]


class SensorState:
    def __init__(self):
        self._lock = threading.Lock()
        self._cap = [0.0] * 4
        self._gsr_mag = [0.0] * 6
        self._gsr_phase = [0.0] * 6

    def set_cap(self, pad_index: int, value: float) -> None:
        with self._lock:
            self._cap[pad_index] = value

    def set_gsr(self, global_pair_index: int, mag: float, phase: float) -> None:
        with self._lock:
            self._gsr_mag[global_pair_index] = mag
            self._gsr_phase[global_pair_index] = phase

    def set_gsr_mag(self, global_pair_index: int, mag: float) -> None:
        with self._lock:
            self._gsr_mag[global_pair_index] = mag

    def set_gsr_phase(self, global_pair_index: int, phase: float) -> None:
        with self._lock:
            self._gsr_phase[global_pair_index] = phase

    def snapshot(self):
        with self._lock:
            return (list(self._cap), list(self._gsr_mag), list(self._gsr_phase))
