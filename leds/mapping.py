"""Sensor-to-LED segment mapping engine."""

from dataclasses import dataclass

# Which global GSR pairs each pad participates in (by pad index 0-3)
PAD_GSR_INDICES = [
    [0, 1, 2],  # Pad 0 (pad 1): pairs (1,2),(1,3),(1,4)
    [0, 3, 4],  # Pad 1 (pad 2): pairs (1,2),(2,3),(2,4)
    [1, 3, 5],  # Pad 2 (pad 3): pairs (1,3),(2,3),(3,4)
    [2, 4, 5],  # Pad 3 (pad 4): pairs (1,4),(2,4),(3,4)
]

_FIXED_IX = 128


@dataclass
class SegmentParams:
    color_r: int
    color_g: int
    color_b: int
    bri: int
    fx: int
    sx: int
    ix: int


def _clamp(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(value))))


class MappingEngine:
    def __init__(self, config: dict):
        self._config = config

    def compute(self, cap, gsr_mag, gsr_phase) -> list:
        # gsr_phase is received but not currently used in the visual mapping
        cfg = self._config
        idle_r, idle_g, idle_b = cfg["idle_color"]
        warm_r, warm_g, warm_b = cfg["warm_color"]
        gsr_r, gsr_g, gsr_b = cfg["gsr_shared_color"]
        min_bri = cfg["min_brightness"]
        max_bri = cfg["max_brightness"]
        idle_effect = cfg["idle_effect"]
        gsr_effect = cfg["gsr_effect"]
        gsr_threshold = cfg["gsr_threshold"]
        speed_min = cfg["speed_min"]
        speed_max = cfg["speed_max"]

        mean_cap = sum(cap) / len(cap)
        sx = _clamp(speed_min + mean_cap * (speed_max - speed_min), 0, 255)

        segments = []
        for pad_idx in range(4):
            cap_val = cap[pad_idx]

            # Brightness
            bri = _clamp(min_bri + cap_val * (max_bri - min_bri), 0, 255)

            # Per-pad GSR: average of the 3 participating pair magnitudes
            indices = PAD_GSR_INDICES[pad_idx]
            per_pad_gsr = sum(gsr_mag[i] for i in indices) / len(indices)

            # Color: idle -> warm by cap, then shift toward gsr_shared by per_pad_gsr
            cap_r = idle_r + cap_val * (warm_r - idle_r)
            cap_g = idle_g + cap_val * (warm_g - idle_g)
            cap_b = idle_b + cap_val * (warm_b - idle_b)

            final_r = _clamp(cap_r + per_pad_gsr * (gsr_r - cap_r), 0, 255)
            final_g = _clamp(cap_g + per_pad_gsr * (gsr_g - cap_g), 0, 255)
            final_b = _clamp(cap_b + per_pad_gsr * (gsr_b - cap_b), 0, 255)

            # Effect
            fx = idle_effect if per_pad_gsr < gsr_threshold else gsr_effect

            segments.append(SegmentParams(
                color_r=final_r,
                color_g=final_g,
                color_b=final_b,
                bri=bri,
                fx=fx,
                sx=sx,
                ix=_FIXED_IX,
            ))

        return segments
