"""HSV color math utilities for LED programs."""

import colorsys
import math


def rgb_to_hsv(rgb: list[int]) -> tuple[float, float, float]:
    """Convert [R, G, B] (0-255 ints) to (H, S, V) with all values 0.0-1.0."""
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    return colorsys.rgb_to_hsv(r, g, b)


def hsv_to_rgb(h: float, s: float, v: float) -> list[int]:
    """Convert (H, S, V) (0.0-1.0) to [R, G, B] (0-255 ints)."""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return [round(r * 255), round(g * 255), round(b * 255)]


def lerp_hsv(c1: list[int], c2: list[int], t: float) -> list[int]:
    """Interpolate between two RGB colors in HSV space.

    Uses shortest-arc hue interpolation — if the two hues are more than
    0.5 apart on the 0-1 wheel, go the short way around. This prevents
    red->cyan from traversing through green.

    t=0 returns c1, t=1 returns c2. t is clamped to [0, 1].
    Returns [R, G, B] as 0-255 ints.
    """
    t = max(0.0, min(1.0, t))
    h1, s1, v1 = rgb_to_hsv(c1)
    h2, s2, v2 = rgb_to_hsv(c2)

    # Shortest-arc hue interpolation
    dh = h2 - h1
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0
    h = (h1 + t * dh) % 1.0

    s = s1 + t * (s2 - s1)
    v = v1 + t * (v2 - v1)
    return hsv_to_rgb(h, s, v)


def group_centroid(colors: list[list[int]]) -> list[int]:
    """Average N RGB colors in HSV space.

    Computes the circular mean of hues (to handle wrap-around correctly),
    and arithmetic mean of S and V.

    Returns [R, G, B] as 0-255 ints.
    Empty input returns [0, 0, 0].
    """
    if not colors:
        return [0, 0, 0]

    sin_sum = 0.0
    cos_sum = 0.0
    s_sum = 0.0
    v_sum = 0.0
    n = len(colors)

    for rgb in colors:
        h, s, v = rgb_to_hsv(rgb)
        angle = h * 2.0 * math.pi
        sin_sum += math.sin(angle)
        cos_sum += math.cos(angle)
        s_sum += s
        v_sum += v

    mean_angle = math.atan2(sin_sum / n, cos_sum / n)
    h_mean = (mean_angle / (2.0 * math.pi)) % 1.0
    s_mean = s_sum / n
    v_mean = v_sum / n

    return hsv_to_rgb(h_mean, s_mean, v_mean)
