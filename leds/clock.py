"""Beat clock with BPM sync and latency compensation."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ClockPhase:
    beat: float  # 0.0-1.0 within current beat
    bar: float   # 0.0-1.0 within 4-beat bar
    bpm: float


class Clock:
    """Beat clock with BPM sync and latency compensation.

    Not thread-safe. Owned by the main render loop; sync() is called
    from the same thread after reading tempo from PadState.snapshot().
    """

    def __init__(self, latency_offset_ms: float = 0.0):
        self._latency_offset_ms = latency_offset_ms
        self._bpm: float = 0.0
        self._sync_time: float | None = None

    @property
    def latency_offset_ms(self) -> float:
        return self._latency_offset_ms

    @latency_offset_ms.setter
    def latency_offset_ms(self, value: float) -> None:
        self._latency_offset_ms = value

    def sync(self, bpm: float, sync_time: float) -> None:
        self._bpm = bpm
        self._sync_time = sync_time

    def phase(self, now: float) -> ClockPhase:
        if self._sync_time is None or self._bpm == 0.0:
            return ClockPhase(beat=0.0, bar=0.0, bpm=0.0)

        adjusted = now + self._latency_offset_ms / 1000.0
        elapsed = adjusted - self._sync_time
        beat_period = 60.0 / self._bpm
        elapsed_beats = elapsed / beat_period

        beat = math.fmod(elapsed_beats, 1.0)
        if beat < 0.0:
            beat += 1.0

        bar = math.fmod(elapsed_beats / 4.0, 1.0)
        if bar < 0.0:
            bar += 1.0

        return ClockPhase(beat=beat, bar=bar, bpm=self._bpm)
