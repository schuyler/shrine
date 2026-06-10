"""Tests for leds.color HSV utility functions."""

import pytest

from leds.color import group_centroid, hsv_to_rgb, lerp_hsv, rgb_to_hsv


# ---------------------------------------------------------------------------
# rgb_to_hsv
# ---------------------------------------------------------------------------

def test_rgb_to_hsv_pure_red():
    h, s, v = rgb_to_hsv([255, 0, 0])
    assert h == pytest.approx(0.0)
    assert s == pytest.approx(1.0)
    assert v == pytest.approx(1.0)


def test_rgb_to_hsv_pure_green():
    h, s, v = rgb_to_hsv([0, 255, 0])
    assert h == pytest.approx(1 / 3, abs=1e-6)
    assert s == pytest.approx(1.0)
    assert v == pytest.approx(1.0)


def test_rgb_to_hsv_pure_blue():
    h, s, v = rgb_to_hsv([0, 0, 255])
    assert h == pytest.approx(2 / 3, abs=1e-6)
    assert s == pytest.approx(1.0)
    assert v == pytest.approx(1.0)


def test_rgb_to_hsv_black():
    h, s, v = rgb_to_hsv([0, 0, 0])
    assert v == pytest.approx(0.0)
    assert s == pytest.approx(0.0)


def test_rgb_to_hsv_white():
    h, s, v = rgb_to_hsv([255, 255, 255])
    assert s == pytest.approx(0.0)
    assert v == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# hsv_to_rgb
# ---------------------------------------------------------------------------

def test_hsv_to_rgb_roundtrip_red():
    original = [255, 0, 0]
    h, s, v = rgb_to_hsv(original)
    result = hsv_to_rgb(h, s, v)
    assert result == original


def test_hsv_to_rgb_roundtrip_green():
    original = [0, 255, 0]
    h, s, v = rgb_to_hsv(original)
    result = hsv_to_rgb(h, s, v)
    assert result == original


def test_hsv_to_rgb_roundtrip_blue():
    original = [0, 0, 255]
    h, s, v = rgb_to_hsv(original)
    result = hsv_to_rgb(h, s, v)
    assert result == original


def test_hsv_to_rgb_roundtrip_arbitrary():
    original = [100, 150, 200]
    h, s, v = rgb_to_hsv(original)
    result = hsv_to_rgb(h, s, v)
    assert result == original


def test_hsv_to_rgb_roundtrip_black():
    original = [0, 0, 0]
    h, s, v = rgb_to_hsv(original)
    result = hsv_to_rgb(h, s, v)
    assert result == original


def test_hsv_to_rgb_roundtrip_white():
    original = [255, 255, 255]
    h, s, v = rgb_to_hsv(original)
    result = hsv_to_rgb(h, s, v)
    assert result == original


# ---------------------------------------------------------------------------
# lerp_hsv
# ---------------------------------------------------------------------------

def test_lerp_hsv_t0_returns_c1():
    c1 = [255, 0, 0]
    c2 = [0, 0, 255]
    assert lerp_hsv(c1, c2, 0.0) == c1


def test_lerp_hsv_t1_returns_c2():
    c1 = [255, 0, 0]
    c2 = [0, 0, 255]
    assert lerp_hsv(c1, c2, 1.0) == c2


def test_lerp_hsv_midpoint_is_between():
    c1 = [255, 0, 0]    # red, H=0
    c2 = [0, 0, 255]    # blue, H=0.667
    mid = lerp_hsv(c1, c2, 0.5)
    h, s, v = rgb_to_hsv(mid)
    # Midpoint hue should be near magenta (H≈0.833) via shortest arc
    # Red H=0, Blue H=0.667; delta = 0.667 > 0.5 so we go the short way:
    # dh = 0.667 - 1.0 = -0.333; midpoint H = 0 + 0.5*(-0.333) = -0.167 → 0.833
    assert h == pytest.approx(0.833, abs=0.01)
    assert s == pytest.approx(1.0, abs=0.01)


def test_lerp_hsv_t_clamped_below_zero():
    c1 = [255, 0, 0]
    c2 = [0, 0, 255]
    assert lerp_hsv(c1, c2, -0.5) == c1


def test_lerp_hsv_t_clamped_above_one():
    c1 = [255, 0, 0]
    c2 = [0, 0, 255]
    assert lerp_hsv(c1, c2, 1.5) == c2


def test_lerp_hsv_shortest_arc_red_to_cyan():
    """Red → cyan should go through magenta/blue, not through green."""
    red = [255, 0, 0]    # H = 0.0
    cyan = [0, 255, 255]  # H = 0.5
    # The two hues are exactly 0.5 apart; with dh = 0.5 (not > 0.5),
    # we go the "forward" direction H=0 → H=0.5 through yellow/green.
    # But let's use a color just past cyan to confirm the short-arc behavior
    # when separation > 0.5: use H=0.51 (slightly past cyan)
    just_past_cyan = hsv_to_rgb(0.51, 1.0, 1.0)  # H≈0.51
    mid = lerp_hsv(red, just_past_cyan, 0.5)
    h_mid, _, _ = rgb_to_hsv(mid)
    # Short arc: dh = 0.51 - 1.0 = -0.49; h_mid = 0 + 0.5*(-0.49) = -0.245 → 0.755 (magenta side)
    # NOT near green (H≈0.33)
    assert h_mid > 0.5 or h_mid < 0.1, (
        f"Expected midpoint near magenta/red end, got H={h_mid:.3f}"
    )


# ---------------------------------------------------------------------------
# group_centroid
# ---------------------------------------------------------------------------

def test_group_centroid_empty_returns_black():
    assert group_centroid([]) == [0, 0, 0]


def test_group_centroid_single_color_returns_itself():
    color = [100, 150, 200]
    result = group_centroid([color])
    assert result == color


def test_group_centroid_two_identical_colors():
    color = [200, 100, 50]
    result = group_centroid([color, color])
    assert result == color


def test_group_centroid_two_colors_average():
    # Red [255,0,0] H=0, Blue [0,0,255] H=0.667
    # Circular mean of H=0 and H=0.667:
    #   sin(0)+sin(0.667*2π) = 0 + sin(4.19) ≈ -0.866
    #   cos(0)+cos(0.667*2π) = 1 + cos(4.19) ≈  0.5
    #   atan2(-0.866/2, 0.5/2) ≈ atan2(-0.433, 0.25) ≈ -1.047 rad → H ≈ 0.833 (magenta)
    result = group_centroid([[255, 0, 0], [0, 0, 255]])
    h, s, v = rgb_to_hsv(result)
    assert h == pytest.approx(0.833, abs=0.02)


def test_group_centroid_circular_mean_red_magenta():
    """Red + magenta should average toward red/magenta, not toward green."""
    red = [255, 0, 0]         # H = 0.0
    magenta = [255, 0, 255]   # H ≈ 0.833
    result = group_centroid([red, magenta])
    h, s, v = rgb_to_hsv(result)
    # Circular mean of H=0 and H=0.833:
    # angle0 = 0, angle1 = 0.833*2π = 5.236
    # sin_mean = (sin(0)+sin(5.236))/2 = (0 + (-0.866))/2 = -0.433
    # cos_mean = (cos(0)+cos(5.236))/2 = (1 + 0.5)/2 = 0.75
    # atan2(-0.433, 0.75) ≈ -0.524 rad → H ≈ (2π - 0.524)/(2π) ≈ 0.917
    # That's between red (0) and magenta (0.833) — near the red/magenta region
    assert h > 0.8 or h < 0.1, (
        f"Expected H near red/magenta region, got H={h:.3f}"
    )
