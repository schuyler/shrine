"""Converge program — group signature colors blend toward centroid."""

from leds.color import group_centroid, lerp_hsv
from leds.programs import Program, SegmentParams, register

# Blend factor by group size. Larger groups blend more strongly.
_BLEND_BY_SIZE = {1: 0.0, 2: 0.3, 3: 0.6, 4: 0.9}


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

        # All pads share the same group frozenset.
        group = pads[0].group if pads else frozenset()

        # Collect signature colors of pads in the group.
        group_colors = []
        for i, pad in enumerate(pads):
            if i in group and pad.signature_color is not None:
                group_colors.append(pad.signature_color)

        centroid = group_centroid(group_colors) if len(group_colors) >= 2 else None
        blend_t = _BLEND_BY_SIZE.get(len(group), 0.9)

        segments = []
        for i, pad in enumerate(pads):
            cap = _clamp(pad.cap, 0.0, 1.0)
            base_color = pad.signature_color if pad.signature_color is not None else idle

            if i in group and centroid is not None:
                # Blend toward group centroid, then slight warm shift with cap
                color = lerp_hsv(base_color, centroid, blend_t)
                color = lerp_hsv(color, warm, cap * 0.15)
                bri = _clamp(round(50 + cap * 205), 50, 255)
            else:
                # Not in group — breathe-like behavior
                color = lerp_hsv(base_color, warm, cap * 0.2)
                bri = _clamp(round(20 + cap * 235), 20, 255)

            segments.append(SegmentParams(col=[color], bri=bri))
        return segments, {}
