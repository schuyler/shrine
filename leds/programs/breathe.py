"""Breathe program — default ambient mode."""

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
        segments = []
        for pad in pads:
            cap = max(0.0, min(1.0, pad.cap))
            bri = _clamp(round(20 + cap * 235), 20, 255)
            color = _lerp_color(idle, warm, cap)
            segments.append(SegmentParams(col=[color], bri=bri))
        return segments, {}
