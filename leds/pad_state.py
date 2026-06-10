"""Per-pad state with thread-safe access."""

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class PadSnapshot:
    cap: float        # 0-1
    heartbeat: float  # Hz, 0 = none
    flux: float       # 0-1
    signature_color: list[int] | None = None
    group: frozenset = frozenset()


@dataclass(frozen=True)
class EffectOverride:
    """A manual WLED effect to force onto a pad, bypassing the program.

    Used for testing the lighting independently of the running program.
    ``col`` of ``None`` means "use the pad's signature color (or white)" —
    resolved by the render loop, which is where signature colors live.
    """
    fx: int
    bri: int = 255
    sx: int = 128
    ix: int = 128
    pal: int = 0
    col: list[list[int]] | None = None


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
        self._signature_colors: dict[int, list[int]] = {}
        self._group: frozenset[int] = frozenset()
        self._effect_overrides: dict[int, EffectOverride] = {}

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

    def set_group(self, members: frozenset[int]) -> None:
        with self._lock:
            self._group = members

    def group(self) -> frozenset[int]:
        with self._lock:
            return self._group

    def set_effect(self, pad: int, override: EffectOverride) -> None:
        with self._lock:
            if pad not in self._index:
                return
            self._effect_overrides[pad] = override

    def clear_effect(self, pad: int) -> None:
        with self._lock:
            self._effect_overrides.pop(pad, None)

    def clear_all_effects(self) -> None:
        with self._lock:
            self._effect_overrides.clear()

    def effect_overrides(self) -> dict[int, EffectOverride]:
        with self._lock:
            return dict(self._effect_overrides)

    def set_signature_colors(self, colors: dict[int, list[int]]) -> None:
        with self._lock:
            self._signature_colors = {
                self._index[pad]: color
                for pad, color in colors.items()
                if pad in self._index
            }

    def snapshot(self) -> tuple:
        with self._lock:
            snapshots = [
                PadSnapshot(
                    cap=self._cap[i],
                    heartbeat=self._heartbeat[i],
                    flux=self._flux[i],
                    signature_color=self._signature_colors.get(i),
                    group=self._group,
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
