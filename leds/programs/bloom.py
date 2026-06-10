"""Bloom program — unison color for the ascending climax."""

import math

from leds.programs import Program, SegmentParams, register

# Default unison target — sage/silver from the event palette.
_DEFAULT_UNISON = [168, 191, 187]


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


@register
class BloomProgram(Program):
    @property
    def name(self) -> str:
        return "bloom"

    def render(self, pads, palette, clock_phase, state):
        # Slow pulse on bar phase (one full cycle per 4 beats)
        pulse = 0.5 + 0.5 * math.sin(clock_phase.bar * 2 * math.pi)
        target = palette.get("unison", _DEFAULT_UNISON)

        segments = []
        for pad in pads:
            bri = _clamp(round(200 + pulse * 55), 200, 255)
            segments.append(SegmentParams(col=[target], bri=bri))
        return segments, {}
