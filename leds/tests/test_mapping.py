import pytest

from leds.mapping import MappingEngine, SegmentParams

TEST_CONFIG = {
    "idle_color": [0, 0, 255],
    "warm_color": [255, 180, 0],
    "gsr_shared_color": [200, 0, 200],
    "min_brightness": 20,
    "max_brightness": 255,
    "idle_effect": 0,
    "gsr_effect": 63,
    "gsr_threshold": 0.1,
    "speed_min": 60,
    "speed_max": 200,
}


class TestSegmentParams:
    def test_has_color_r(self):
        p = SegmentParams(color_r=10, color_g=20, color_b=30, bri=100, fx=0, sx=60, ix=128)
        assert p.color_r == 10

    def test_has_color_g(self):
        p = SegmentParams(color_r=10, color_g=20, color_b=30, bri=100, fx=0, sx=60, ix=128)
        assert p.color_g == 20

    def test_has_color_b(self):
        p = SegmentParams(color_r=10, color_g=20, color_b=30, bri=100, fx=0, sx=60, ix=128)
        assert p.color_b == 30

    def test_has_bri(self):
        p = SegmentParams(color_r=10, color_g=20, color_b=30, bri=100, fx=0, sx=60, ix=128)
        assert p.bri == 100

    def test_has_fx(self):
        p = SegmentParams(color_r=10, color_g=20, color_b=30, bri=100, fx=0, sx=60, ix=128)
        assert p.fx == 0

    def test_has_sx(self):
        p = SegmentParams(color_r=10, color_g=20, color_b=30, bri=100, fx=0, sx=60, ix=128)
        assert p.sx == 60

    def test_has_ix(self):
        p = SegmentParams(color_r=10, color_g=20, color_b=30, bri=100, fx=0, sx=60, ix=128)
        assert p.ix == 128


class TestMappingEngineOutput:
    def test_compute_returns_list_of_4(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        assert len(result) == 4

    def test_compute_returns_segment_params_instances(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for item in result:
            assert isinstance(item, SegmentParams)


class TestAllZerosInput:
    def test_idle_color_r(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.color_r == TEST_CONFIG["idle_color"][0]

    def test_idle_color_g(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.color_g == TEST_CONFIG["idle_color"][1]

    def test_idle_color_b(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.color_b == TEST_CONFIG["idle_color"][2]

    def test_min_brightness(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.bri == TEST_CONFIG["min_brightness"]

    def test_idle_effect(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.fx == TEST_CONFIG["idle_effect"]


class TestFullCapNoGsr:
    def test_warm_color_r(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.color_r == TEST_CONFIG["warm_color"][0]

    def test_warm_color_g(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.color_g == TEST_CONFIG["warm_color"][1]

    def test_warm_color_b(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.color_b == TEST_CONFIG["warm_color"][2]

    def test_max_brightness(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.bri == TEST_CONFIG["max_brightness"]

    def test_idle_effect_without_gsr(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.fx == TEST_CONFIG["idle_effect"]


class TestFullCapFullGsr:
    def test_gsr_effect(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [1.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.fx == TEST_CONFIG["gsr_effect"]

    def test_max_brightness_with_gsr(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [1.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.bri == TEST_CONFIG["max_brightness"]

    def test_gsr_color_influence(self):
        """With full GSR, color should show gsr_shared_color influence (not idle_color)."""
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [1.0] * 6, [0.0] * 6)
        # At full GSR, color must differ from idle_color in at least one channel
        idle = TEST_CONFIG["idle_color"]
        for seg in result:
            assert (seg.color_r, seg.color_g, seg.color_b) != tuple(idle)


class TestBrightnessScaling:
    def test_brightness_scales_linearly_with_cap(self):
        """Brightness should increase monotonically as cap increases from 0 to 1."""
        engine = MappingEngine(TEST_CONFIG)
        min_bri = TEST_CONFIG["min_brightness"]
        max_bri = TEST_CONFIG["max_brightness"]

        for cap_val in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = engine.compute([cap_val] * 4, [0.0] * 6, [0.0] * 6)
            expected_bri = min_bri + cap_val * (max_bri - min_bri)
            for seg in result:
                assert seg.bri == pytest.approx(expected_bri, abs=2), (
                    f"cap={cap_val}: expected bri ~{expected_bri}, got {seg.bri}"
                )

    def test_brightness_at_zero_is_min(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.bri == TEST_CONFIG["min_brightness"]

    def test_brightness_at_full_is_max(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.bri == TEST_CONFIG["max_brightness"]


class TestSpeedScaling:
    def test_speed_scales_with_mean_cap(self):
        """sx should increase monotonically with mean cap value."""
        engine = MappingEngine(TEST_CONFIG)
        speed_min = TEST_CONFIG["speed_min"]
        speed_max = TEST_CONFIG["speed_max"]

        for cap_val in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = engine.compute([cap_val] * 4, [0.0] * 6, [0.0] * 6)
            expected_sx = speed_min + cap_val * (speed_max - speed_min)
            for seg in result:
                assert seg.sx == pytest.approx(expected_sx, abs=2), (
                    f"cap_mean={cap_val}: expected sx ~{expected_sx}, got {seg.sx}"
                )

    def test_speed_at_zero_cap_is_speed_min(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.sx == TEST_CONFIG["speed_min"]

    def test_speed_at_full_cap_is_speed_max(self):
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0] * 4, [0.0] * 6, [0.0] * 6)
        for seg in result:
            assert seg.sx == TEST_CONFIG["speed_max"]

    def test_speed_uses_mean_of_all_caps(self):
        """Only pad 0 active: mean = 0.25; speed should reflect the mean, not pad 0 alone."""
        engine = MappingEngine(TEST_CONFIG)
        result = engine.compute([1.0, 0.0, 0.0, 0.0], [0.0] * 6, [0.0] * 6)
        speed_min = TEST_CONFIG["speed_min"]
        speed_max = TEST_CONFIG["speed_max"]
        expected = speed_min + 0.25 * (speed_max - speed_min)
        for seg in result:
            assert seg.sx == pytest.approx(expected, abs=2)


class TestPerPadGsrMapping:
    """
    Each pad's GSR is the average of the 3 pairs it participates in:
      Pad 0 (pad 1): global pairs 0, 1, 2
      Pad 1 (pad 2): global pairs 0, 3, 4
      Pad 2 (pad 3): global pairs 1, 3, 5
      Pad 3 (pad 4): global pairs 2, 4, 5
    """

    def _make_gsr_mag(self, active_indices, value=1.0):
        mag = [0.0] * 6
        for i in active_indices:
            mag[i] = value
        return mag

    def test_pad0_gsr_from_pairs_0_1_2(self):
        """Pad 0 segment should show GSR effect when pairs 0,1,2 are active."""
        engine = MappingEngine(TEST_CONFIG)
        mag = self._make_gsr_mag([0, 1, 2], value=1.0)
        result = engine.compute([1.0] * 4, mag, [0.0] * 6)
        assert result[0].fx == TEST_CONFIG["gsr_effect"]

    def test_pad1_gsr_from_pairs_0_3_4(self):
        """Pad 1 segment should show GSR effect when pairs 0,3,4 are active."""
        engine = MappingEngine(TEST_CONFIG)
        mag = self._make_gsr_mag([0, 3, 4], value=1.0)
        result = engine.compute([1.0] * 4, mag, [0.0] * 6)
        assert result[1].fx == TEST_CONFIG["gsr_effect"]

    def test_pad2_gsr_from_pairs_1_3_5(self):
        """Pad 2 segment should show GSR effect when pairs 1,3,5 are active."""
        engine = MappingEngine(TEST_CONFIG)
        mag = self._make_gsr_mag([1, 3, 5], value=1.0)
        result = engine.compute([1.0] * 4, mag, [0.0] * 6)
        assert result[2].fx == TEST_CONFIG["gsr_effect"]

    def test_pad3_gsr_from_pairs_2_4_5(self):
        """Pad 3 segment should show GSR effect when pairs 2,4,5 are active."""
        engine = MappingEngine(TEST_CONFIG)
        mag = self._make_gsr_mag([2, 4, 5], value=1.0)
        result = engine.compute([1.0] * 4, mag, [0.0] * 6)
        assert result[3].fx == TEST_CONFIG["gsr_effect"]

    def test_pad0_no_gsr_when_irrelevant_pairs_active(self):
        """Pairs 3,4,5 don't involve pad 0; pad 0 segment should not trigger GSR effect."""
        engine = MappingEngine(TEST_CONFIG)
        mag = self._make_gsr_mag([3, 4, 5], value=1.0)
        result = engine.compute([1.0] * 4, mag, [0.0] * 6)
        assert result[0].fx == TEST_CONFIG["idle_effect"]


class TestIxField:
    def test_ix_has_consistent_value(self):
        """ix should be a fixed value across all segments and inputs.

        The design spec does not define a computation for ix; it is treated as
        a fixed WLED effect-intensity default (128).
        """
        engine = MappingEngine(TEST_CONFIG)

        inputs = [
            ([0.0] * 4, [0.0] * 6, [0.0] * 6),
            ([1.0] * 4, [1.0] * 6, [0.0] * 6),
            ([0.5] * 4, [0.3] * 6, [1.0] * 6),
        ]
        ix_values = set()
        for cap, mag, phase in inputs:
            result = engine.compute(cap, mag, phase)
            for seg in result:
                ix_values.add(seg.ix)

        assert len(ix_values) == 1, (
            f"ix should be the same fixed value for all segments and inputs, "
            f"but got multiple values: {ix_values}"
        )


class TestPureFunction:
    def test_same_inputs_same_outputs(self):
        engine = MappingEngine(TEST_CONFIG)
        cap = [0.3, 0.5, 0.7, 0.2]
        mag = [0.1, 0.4, 0.6, 0.2, 0.8, 0.3]
        phase = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

        result1 = engine.compute(cap, mag, phase)
        result2 = engine.compute(cap, mag, phase)

        for s1, s2 in zip(result1, result2):
            assert (s1.color_r, s1.color_g, s1.color_b, s1.bri, s1.fx, s1.sx, s1.ix) == (
                s2.color_r,
                s2.color_g,
                s2.color_b,
                s2.bri,
                s2.fx,
                s2.sx,
                s2.ix,
            )

    def test_different_inputs_can_produce_different_outputs(self):
        engine = MappingEngine(TEST_CONFIG)
        result_zero = engine.compute([0.0] * 4, [0.0] * 6, [0.0] * 6)
        result_full = engine.compute([1.0] * 4, [1.0] * 6, [0.0] * 6)
        assert result_zero[0].bri != result_full[0].bri
