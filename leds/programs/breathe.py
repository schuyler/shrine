"""Breathe program — default ambient mode."""

from leds.program_config import get_program_params, resolve_ix, resolve_sx
from leds.programs import Program, SegmentParams, register


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _lerp_color(a: list[int], b: list[int], t: float) -> list[int]:
    return [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]


@register
class BreatheProgram(Program):
    @property
    def name(self) -> str:
        return "breathe"

    def render(self, pads, palette, clock_phase, state: dict) -> tuple[list[SegmentParams], dict]:
        idle = palette.get("idle")
        warm = palette.get("warm")
        params = get_program_params("breathe")
        sx = resolve_sx(params, clock_phase.bpm)
        ix = resolve_ix(params, clock_phase.bpm)
        segments = []
        for pad in pads:
            cap = max(0.0, min(1.0, pad.cap))
            bri = _clamp(round(20 + cap * 235), 20, 255)
            base_color = pad.signature_color if pad.signature_color is not None else idle
            color = _lerp_color(base_color, warm, cap)
            segments.append(SegmentParams(col=[color], bri=bri, fx="twinkleup", sx=sx, ix=ix))
        return segments, {}
