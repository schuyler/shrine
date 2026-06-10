"""Converge program — colorwaves across connected participants' signature colors."""

from leds.color import lerp_hsv
from leds.program_config import get_program_params, resolve_ix, resolve_sx
from leds.programs import Program, SegmentParams, register


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


@register
class ConvergeProgram(Program):
    @property
    def name(self) -> str:
        return "converge"

    def render(self, pads, palette, clock_phase, state):
        idle = palette.get("idle")
        warm = palette.get("warm")
        params = get_program_params("converge")
        sx = resolve_sx(params, clock_phase.bpm)
        ix = resolve_ix(params, clock_phase.bpm)

        # All pads share the same group frozenset.
        group = pads[0].group if pads else frozenset()

        # Collect signature colors of pads in the group.
        group_colors = []
        for i, pad in enumerate(pads):
            if i in group and pad.signature_color is not None:
                group_colors.append(pad.signature_color)

        segments = []
        for i, pad in enumerate(pads):
            cap = _clamp(pad.cap, 0.0, 1.0)
            base_color = pad.signature_color if pad.signature_color is not None else idle

            if i in group and len(group_colors) >= 2:
                # Colorwaves across both participants' signature colors
                bri = _clamp(round(50 + cap * 205), 50, 255)
                segments.append(SegmentParams(
                    col=group_colors[:2], bri=bri, fx="colorwaves", sx=sx, ix=ix,
                ))
            else:
                # Not in group — breathe-like behavior
                color = lerp_hsv(base_color, warm, cap * 0.2)
                bri = _clamp(round(20 + cap * 235), 20, 255)
                segments.append(SegmentParams(col=[color], bri=bri))

        return segments, {}
