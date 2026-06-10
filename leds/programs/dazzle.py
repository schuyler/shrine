"""Dazzle program — rotating color wheel across stations at beat speed.

All four boxes lit solid at full brightness. Each beat, the color
assignment shifts one station around the ring: what was on pad 0
moves to pad 1, pad 1's color moves to pad 2, etc. The colors are
the four signature colors from the pads, so the event palette
itself spins around the installation.
"""

import math

from leds.programs import Program, SegmentParams, register


@register
class DazzleProgram(Program):
    @property
    def name(self) -> str:
        return "dazzle"

    def render(self, pads, palette, clock_phase, state):
        n = len(pads)
        if n == 0:
            return [], {}

        # Collect signature colors in pad order; fall back to palette idle.
        idle = palette.get("idle")
        colors = [
            pad.signature_color if pad.signature_color is not None else idle
            for pad in pads
        ]

        # Rotation offset: one shift per beat.  beat phase is 0-1 within
        # a single beat, and we want a discrete step per beat.  Use the
        # bar phase (0-1 over 4 beats) × n to get a continuously advancing
        # index, then floor it for hard cuts.
        #
        # bar phase 0.00 → beat 0 → offset 0
        # bar phase 0.25 → beat 1 → offset 1
        # bar phase 0.50 → beat 2 → offset 2
        # bar phase 0.75 → beat 3 → offset 3
        # Then it wraps.
        offset = int(clock_phase.bar * n) % n

        segments = []
        for i in range(n):
            color = colors[(i - offset) % n]
            segments.append(SegmentParams(col=[color], bri=255))
        return segments, {}
