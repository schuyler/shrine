"""Pulse program — slow comet on active pads for the Seeking phase."""

from leds.color import lerp_hsv
from leds.program_config import get_program_params, resolve_ix, resolve_sx
from leds.programs import Program, SegmentParams, register

_CAP_THRESHOLD = 0.05


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


@register
class PulseProgram(Program):
    @property
    def name(self) -> str:
        return "pulse"

    def render(self, pads, palette, clock_phase, state):
        idle = palette.get("idle")
        warm = palette.get("warm")
        params = get_program_params("pulse")
        sx = resolve_sx(params, clock_phase.bpm)
        ix = resolve_ix(params, clock_phase.bpm)
        segments = []
        for pad in pads:
            cap = _clamp(pad.cap, 0.0, 1.0)
            base_color = pad.signature_color if pad.signature_color is not None else idle
            if cap > _CAP_THRESHOLD:
                # Active pad: slow comet in signature color
                color = lerp_hsv(base_color, warm, cap * 0.3)
                bri = _clamp(round(80 + cap * 175), 80, 255)
                segments.append(SegmentParams(
                    col=[color], bri=bri, fx="Meteor", sx=sx, ix=ix,
                ))
            else:
                # Inactive pad: dim breathe-like glow
                segments.append(SegmentParams(col=[base_color], bri=20))
        return segments, {}
