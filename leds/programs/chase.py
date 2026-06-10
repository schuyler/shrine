"""Chase program — WLED built-in chase effect driven by heartbeat tempo."""

from leds.programs import Program, SegmentParams, register

_WLED_CHASE_FX = "Chase"

# Heartbeat Hz → WLED sx mapping.  Empirical starting point; needs tuning.
_HB_LO = 0.5   # Hz
_HB_HI = 3.0   # Hz
_SX_LO = 60
_SX_HI = 200


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _lerp_color(a: list[int], b: list[int], t: float) -> list[int]:
    return [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]


def _heartbeat_to_sx(hz: float) -> int:
    t = (hz - _HB_LO) / (_HB_HI - _HB_LO)
    t = _clamp(t, 0.0, 1.0)
    return round(_SX_LO + t * (_SX_HI - _SX_LO))


@register
class ChaseProgram(Program):
    @property
    def name(self) -> str:
        return "chase"

    def render(self, pads, palette, clock_phase, state: dict) -> tuple[list[SegmentParams], dict]:
        idle = palette.get("idle")
        warm = palette.get("warm")
        segments = []
        for pad in pads:
            if pad.heartbeat > 0:
                color = pad.signature_color if pad.signature_color is not None else idle
                segments.append(SegmentParams(
                    col=[color],
                    bri=255,
                    fx=_WLED_CHASE_FX,
                    sx=_heartbeat_to_sx(pad.heartbeat),
                ))
            else:
                cap = _clamp(pad.cap, 0.0, 1.0)
                bri = _clamp(round(20 + cap * 235), 20, 255)
                base_color = pad.signature_color if pad.signature_color is not None else idle
                color = _lerp_color(base_color, warm, cap)
                segments.append(SegmentParams(col=[color], bri=bri))
        return segments, {}
