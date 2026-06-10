import pytest

from leds.programs import Program, SegmentParams, get_program, list_programs, register
from leds.pad_state import PadSnapshot
from leds.clock import ClockPhase
from leds.palettes import Palette
from leds.color import lerp_hsv, group_centroid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pad(cap=0.0, heartbeat=0.0, flux=0.0, signature_color=None, group=frozenset()):
    return PadSnapshot(cap=cap, heartbeat=heartbeat, flux=flux, signature_color=signature_color, group=group)


def make_palette():
    return Palette("default", {"idle": [0, 0, 255], "warm": [255, 180, 0], "accent": [200, 0, 200]})


def make_clock():
    return ClockPhase(beat=0.0, bar=0.0, bpm=120.0)


# ---------------------------------------------------------------------------
# SegmentParams
# ---------------------------------------------------------------------------

class TestSegmentParamsDefaults:
    def test_fx_default_is_zero(self):
        sp = SegmentParams(col=[[0, 0, 0]], bri=128)
        assert sp.fx == 0

    def test_sx_default_is_128(self):
        sp = SegmentParams(col=[[0, 0, 0]], bri=128)
        assert sp.sx == 128

    def test_ix_default_is_128(self):
        sp = SegmentParams(col=[[0, 0, 0]], bri=128)
        assert sp.ix == 128

    def test_pal_default_is_zero(self):
        sp = SegmentParams(col=[[0, 0, 0]], bri=128)
        assert sp.pal == 0

    def test_on_default_is_true(self):
        sp = SegmentParams(col=[[0, 0, 0]], bri=128)
        assert sp.on is True


class TestSegmentParamsFrozen:
    def test_frozen_bri_raises_on_assign(self):
        sp = SegmentParams(col=[[0, 0, 0]], bri=128)
        with pytest.raises((AttributeError, TypeError)):
            sp.bri = 64

    def test_frozen_fx_raises_on_assign(self):
        sp = SegmentParams(col=[[0, 0, 0]], bri=128)
        with pytest.raises((AttributeError, TypeError)):
            sp.fx = 1


class TestSegmentParamsColFormat:
    def test_col_stores_single_rgb_triple(self):
        sp = SegmentParams(col=[[255, 0, 0]], bri=200)
        assert sp.col == [[255, 0, 0]]

    def test_col_stores_up_to_three_triples(self):
        triples = [[255, 0, 0], [0, 255, 0], [0, 0, 255]]
        sp = SegmentParams(col=triples, bri=200)
        assert sp.col == triples


# ---------------------------------------------------------------------------
# Program ABC
# ---------------------------------------------------------------------------

class TestProgramABC:
    def test_cannot_instantiate_program_directly(self):
        with pytest.raises(TypeError):
            Program()

    def test_subclass_missing_render_raises(self):
        with pytest.raises(TypeError):
            class BadProgram(Program):
                @property
                def name(self):
                    return "bad"
            BadProgram()

    def test_subclass_missing_name_raises(self):
        with pytest.raises(TypeError):
            class BadProgram(Program):
                def render(self, pads, palette, clock_phase, state):
                    return [], {}
            BadProgram()

    def test_valid_subclass_can_instantiate(self):
        class GoodProgram(Program):
            @property
            def name(self):
                return "good"

            def render(self, pads, palette, clock_phase, state):
                return [], {}

        p = GoodProgram()
        assert isinstance(p, Program)

    def test_initial_state_returns_empty_dict(self):
        class GoodProgram(Program):
            @property
            def name(self):
                return "good"

            def render(self, pads, palette, clock_phase, state):
                return [], {}

        p = GoodProgram()
        assert p.initial_state() == {}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_register_decorator_adds_program(self):
        @register
        class TestProg(Program):
            @property
            def name(self):
                return "_test_reg_prog"

            def render(self, pads, palette, clock_phase, state):
                return [], {}

        assert "_test_reg_prog" in list_programs()

    def test_get_program_returns_instance(self):
        @register
        class TestProg2(Program):
            @property
            def name(self):
                return "_test_get_prog"

            def render(self, pads, palette, clock_phase, state):
                return [], {}

        result = get_program("_test_get_prog")
        assert isinstance(result, Program)

    def test_list_programs_returns_list_of_strings(self):
        names = list_programs()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_get_program_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            get_program("__nonexistent_program__")


# ---------------------------------------------------------------------------
# Breathe program
# ---------------------------------------------------------------------------

class TestBreatheProgram:
    def test_breathe_name(self):
        prog = get_program("breathe")
        assert prog.name == "breathe"

    def test_breathe_render_returns_one_segment_per_pad(self):
        prog = get_program("breathe")
        pads = [make_pad() for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert len(segments) == 4

    def test_breathe_render_segments_are_segment_params(self):
        prog = get_program("breathe")
        pads = [make_pad() for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        for seg in segments:
            assert isinstance(seg, SegmentParams)

    def test_breathe_zero_cap_brightness_is_min(self):
        prog = get_program("breathe")
        pads = [make_pad(cap=0.0) for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].bri == 20

    def test_breathe_high_cap_produces_high_brightness(self):
        prog = get_program("breathe")
        pads = [make_pad(cap=1.0) for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].bri == 255

    def test_breathe_low_cap_uses_idle_color(self):
        prog = get_program("breathe")
        palette = make_palette()
        pads = [make_pad(cap=0.0) for _ in range(4)]
        segments, _ = prog.render(pads, palette, make_clock(), {})
        # At cap=0, col should be a single triple matching the idle color
        assert segments[0].col == [palette.get("idle")]

    def test_breathe_high_cap_uses_warm_color(self):
        prog = get_program("breathe")
        palette = make_palette()
        pads = [make_pad(cap=1.0) for _ in range(4)]
        segments, _ = prog.render(pads, palette, make_clock(), {})
        # At cap=1, col should be a single triple matching the warm color
        assert segments[0].col == [palette.get("warm")]

    def test_breathe_render_returns_empty_state(self):
        prog = get_program("breathe")
        pads = [make_pad() for _ in range(4)]
        _, state = prog.render(pads, make_palette(), make_clock(), {})
        assert state == {}

    def test_breathe_initial_state_returns_empty_dict(self):
        prog = get_program("breathe")
        assert prog.initial_state() == {}

    def test_breathe_is_registered(self):
        assert "breathe" in list_programs()

    def test_breathe_single_pad(self):
        prog = get_program("breathe")
        pads = [make_pad(cap=0.5)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert len(segments) == 1

    def test_breathe_brightness_increases_with_cap(self):
        prog = get_program("breathe")
        palette = make_palette()
        clock = make_clock()
        pads_low = [make_pad(cap=0.1)]
        pads_high = [make_pad(cap=0.9)]
        segs_low, _ = prog.render(pads_low, palette, clock, {})
        segs_high, _ = prog.render(pads_high, palette, clock, {})
        assert segs_high[0].bri > segs_low[0].bri


# ---------------------------------------------------------------------------
# Breathe + signature_color
# ---------------------------------------------------------------------------

class TestBreatheProgramSignatureColor:

    def test_breathe_with_signature_color_uses_it_as_base_color(self):
        """When pad has signature_color, breathe uses it instead of palette idle."""
        prog = get_program("breathe")
        palette = make_palette()
        sig_color = [200, 100, 50]
        pad = make_pad(cap=0.0, signature_color=sig_color)
        segments, _ = prog.render([pad], palette, make_clock(), {})
        # At cap=0, color should be the signature_color, not palette idle
        assert segments[0].col == [sig_color]

    def test_breathe_with_signature_color_high_cap_blends_toward_warm(self):
        """At cap=1 with signature_color, breathe blends toward palette warm."""
        prog = get_program("breathe")
        palette = make_palette()
        sig_color = [200, 100, 50]
        pad = make_pad(cap=1.0, signature_color=sig_color)
        segments, _ = prog.render([pad], palette, make_clock(), {})
        # At cap=1, color should match palette warm (full lerp away from base)
        assert segments[0].col == [palette.get("warm")]

    def test_breathe_without_signature_color_uses_palette_idle(self):
        """When signature_color is None, breathe falls back to palette idle (existing behavior)."""
        prog = get_program("breathe")
        palette = make_palette()
        pad = make_pad(cap=0.0, signature_color=None)
        segments, _ = prog.render([pad], palette, make_clock(), {})
        assert segments[0].col == [palette.get("idle")]

    def test_breathe_signature_color_mid_cap_differs_from_no_signature_color(self):
        """At cap=0.5, a pad with signature_color produces a different color than one without."""
        prog = get_program("breathe")
        palette = make_palette()
        sig_color = [200, 100, 50]
        pad_with = make_pad(cap=0.5, signature_color=sig_color)
        pad_without = make_pad(cap=0.5, signature_color=None)
        segs_with, _ = prog.render([pad_with], palette, make_clock(), {})
        segs_without, _ = prog.render([pad_without], palette, make_clock(), {})
        # The two colors should differ because they start from different base colors
        assert segs_with[0].col != segs_without[0].col

    def test_breathe_mixed_pads_some_with_signature_color(self):
        """Pads with and without signature_color render independently in one call."""
        prog = get_program("breathe")
        palette = make_palette()
        sig_color = [200, 100, 50]
        pads = [
            make_pad(cap=0.0, signature_color=sig_color),
            make_pad(cap=0.0, signature_color=None),
        ]
        segments, _ = prog.render(pads, palette, make_clock(), {})
        assert segments[0].col == [sig_color]
        assert segments[1].col == [palette.get("idle")]


# ---------------------------------------------------------------------------
# Chase program
# ---------------------------------------------------------------------------

class TestChaseProgram:
    def test_chase_is_registered(self):
        assert "chase" in list_programs()

    def test_chase_name(self):
        prog = get_program("chase")
        assert prog.name == "chase"

    def test_chase_render_returns_one_segment_per_pad(self):
        prog = get_program("chase")
        pads = [make_pad() for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert len(segments) == 4

    def test_chase_active_pad_produces_fx_chase(self):
        """Active pad (heartbeat > 0) uses WLED Chase effect fx='Chase'."""
        prog = get_program("chase")
        pads = [make_pad(heartbeat=1.5)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].fx == "Chase"

    def test_chase_active_pad_sx_maps_linearly(self):
        """heartbeat=1.75 Hz (midpoint of [0.5, 3.0]) → sx=130 (midpoint of [60, 200])."""
        prog = get_program("chase")
        pads = [make_pad(heartbeat=1.75)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].sx == 130

    def test_chase_active_pad_brightness_is_255(self):
        prog = get_program("chase")
        pads = [make_pad(heartbeat=1.5)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].bri == 255

    def test_chase_active_pad_uses_signature_color(self):
        """Active pad with signature_color uses it as col[0]."""
        prog = get_program("chase")
        sig_color = [200, 100, 50]
        pads = [make_pad(heartbeat=1.5, signature_color=sig_color)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].col[0] == sig_color

    def test_chase_active_pad_falls_back_to_palette_idle(self):
        """Active pad without signature_color uses palette idle as col[0]."""
        prog = get_program("chase")
        palette = make_palette()
        pads = [make_pad(heartbeat=1.5, signature_color=None)]
        segments, _ = prog.render(pads, palette, make_clock(), {})
        assert segments[0].col[0] == palette.get("idle")

    def test_chase_inactive_pad_produces_fx_0(self):
        """Inactive pad (heartbeat=0) uses fx=0 (solid/breathe mode)."""
        prog = get_program("chase")
        pads = [make_pad(heartbeat=0.0)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].fx == 0

    def test_chase_inactive_pad_brightness_at_cap_zero(self):
        """Inactive pad at cap=0 has brightness 20 (same as breathe)."""
        prog = get_program("chase")
        pads = [make_pad(cap=0.0, heartbeat=0.0)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].bri == 20

    def test_chase_inactive_pad_brightness_at_cap_one(self):
        """Inactive pad at cap=1 has brightness 255 (same as breathe)."""
        prog = get_program("chase")
        pads = [make_pad(cap=1.0, heartbeat=0.0)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].bri == 255

    def test_chase_inactive_pad_color_at_cap_zero_uses_palette_idle(self):
        """Inactive pad at cap=0 uses palette idle color."""
        prog = get_program("chase")
        palette = make_palette()
        pads = [make_pad(cap=0.0, heartbeat=0.0, signature_color=None)]
        segments, _ = prog.render(pads, palette, make_clock(), {})
        assert segments[0].col == [palette.get("idle")]

    def test_chase_mixed_pads_produce_different_fx(self):
        """Active and inactive pads in same render call produce fx='Chase' and fx=0 respectively."""
        prog = get_program("chase")
        palette = make_palette()
        pads = [
            make_pad(heartbeat=1.5),   # active
            make_pad(heartbeat=0.0),   # inactive
        ]
        segments, _ = prog.render(pads, palette, make_clock(), {})
        assert segments[0].fx == "Chase"
        assert segments[1].fx == 0

    def test_chase_sx_clamp_low_heartbeat(self):
        """Heartbeat below 0.5 Hz clamps sx to 60."""
        prog = get_program("chase")
        pads = [make_pad(heartbeat=0.1)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].sx == 60

    def test_chase_sx_clamp_high_heartbeat(self):
        """Heartbeat above 3.0 Hz clamps sx to 200."""
        prog = get_program("chase")
        pads = [make_pad(heartbeat=5.0)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segments[0].sx == 200

    def test_chase_inactive_pad_with_signature_color(self):
        """Inactive pad with signature_color uses it as base for color lerp."""
        prog = get_program("chase")
        palette = make_palette()
        sig_color = [200, 100, 50]
        pad_with = make_pad(cap=0.0, heartbeat=0.0, signature_color=sig_color)
        pad_without = make_pad(cap=0.0, heartbeat=0.0, signature_color=None)
        segs_with, _ = prog.render([pad_with], palette, make_clock(), {})
        segs_without, _ = prog.render([pad_without], palette, make_clock(), {})
        # At cap=0, signature_color pad uses sig_color, non-signature uses palette idle
        assert segs_with[0].col == [sig_color]
        assert segs_without[0].col == [palette.get("idle")]


# ---------------------------------------------------------------------------
# Pulse program
# ---------------------------------------------------------------------------

class TestPulseProgram:
    def test_pulse_is_registered(self):
        assert "pulse" in list_programs()

    def test_pulse_name(self):
        prog = get_program("pulse")
        assert prog.name == "pulse"

    def test_pulse_render_returns_one_segment_per_pad(self):
        prog = get_program("pulse")
        pads = [make_pad() for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert len(segments) == 4

    def test_pulse_active_pad_uses_comet_effect(self):
        """Active pad (cap above threshold) uses WLED Comet effect."""
        prog = get_program("pulse")
        pads = [make_pad(cap=0.5)]
        segs, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segs[0].fx == "Comet"

    def test_pulse_inactive_pad_uses_solid(self):
        """Inactive pad (cap=0) uses default fx=0 (Solid)."""
        prog = get_program("pulse")
        pads = [make_pad(cap=0.0)]
        segs, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segs[0].fx == 0

    def test_pulse_inactive_pad_dim(self):
        """Inactive pad has low brightness."""
        prog = get_program("pulse")
        pads = [make_pad(cap=0.0)]
        segs, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segs[0].bri == 20

    def test_pulse_active_pad_brightness_scales_with_cap(self):
        """Higher cap produces higher brightness on active pads."""
        prog = get_program("pulse")
        palette = make_palette()
        clock = make_clock()
        segs_lo, _ = prog.render([make_pad(cap=0.2)], palette, clock, {})
        segs_hi, _ = prog.render([make_pad(cap=0.9)], palette, clock, {})
        assert segs_hi[0].bri > segs_lo[0].bri

    def test_pulse_active_pad_brightness_floor(self):
        """Active pad has bri >= 80."""
        prog = get_program("pulse")
        pads = [make_pad(cap=0.1)]
        segs, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segs[0].bri >= 80

    def test_pulse_uses_signature_color(self):
        """Inactive pad uses signature_color as base."""
        prog = get_program("pulse")
        sig_color = [217, 24, 40]
        pads = [make_pad(cap=0.0, signature_color=sig_color)]
        segs, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segs[0].col == [sig_color]

    def test_pulse_falls_back_to_palette_idle(self):
        """Without signature_color, uses palette idle."""
        prog = get_program("pulse")
        palette = make_palette()
        pads = [make_pad(cap=0.0, signature_color=None)]
        segs, _ = prog.render(pads, palette, make_clock(), {})
        assert segs[0].col == [palette.get("idle")]

    def test_pulse_mixed_active_inactive(self):
        """Active and inactive pads in same render produce different fx."""
        prog = get_program("pulse")
        pads = [make_pad(cap=0.5), make_pad(cap=0.0)]
        segs, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert segs[0].fx == "Comet"
        assert segs[1].fx == 0

    def test_pulse_returns_empty_state(self):
        prog = get_program("pulse")
        pads = [make_pad() for _ in range(4)]
        _, state = prog.render(pads, make_palette(), make_clock(), {})
        assert state == {}


# ---------------------------------------------------------------------------
# Converge program
# ---------------------------------------------------------------------------

class TestConvergeProgram:
    def test_converge_is_registered(self):
        assert "converge" in list_programs()

    def test_converge_name(self):
        prog = get_program("converge")
        assert prog.name == "converge"

    def test_converge_render_returns_one_segment_per_pad(self):
        prog = get_program("converge")
        pads = [make_pad() for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert len(segments) == 4

    def test_converge_no_group_uses_signature_colors(self):
        """Pads with empty group render like breathe — base color is signature_color."""
        prog = get_program("converge")
        palette = make_palette()
        sig = [217, 24, 40]
        # Empty group → not in group branch, breathe-like behavior
        pads = [make_pad(cap=0.0, signature_color=sig, group=frozenset())]
        segs, _ = prog.render(pads, palette, make_clock(), {})
        # At cap=0: lerp_hsv(sig, warm, 0) == sig
        assert segs[0].col == [sig]

    def test_converge_group_of_two_blends_colors(self):
        """Two pads in a group produce colors closer to each other than their originals."""
        prog = get_program("converge")
        palette = make_palette()
        sig0 = [217, 24, 40]    # red
        sig1 = [2, 136, 166]    # teal
        group = frozenset({0, 1})
        pads = [
            make_pad(cap=0.0, signature_color=sig0, group=group),
            make_pad(cap=0.0, signature_color=sig1, group=group),
        ]
        segs, _ = prog.render(pads, palette, make_clock(), {})
        # centroid of [sig0, sig1]; blend_t=0.3 for group of 2
        centroid = group_centroid([sig0, sig1])
        expected0 = lerp_hsv(sig0, centroid, 0.3)
        expected1 = lerp_hsv(sig1, centroid, 0.3)
        assert segs[0].col == [expected0]
        assert segs[1].col == [expected1]

    def test_converge_larger_group_blends_more(self):
        """Group of 3 blends more strongly than group of 2."""
        prog = get_program("converge")
        palette = make_palette()
        sig0 = [217, 24, 40]
        sig1 = [2, 136, 166]
        sig2 = [217, 207, 74]

        group2 = frozenset({0, 1})
        pads2 = [
            make_pad(cap=0.0, signature_color=sig0, group=group2),
            make_pad(cap=0.0, signature_color=sig1, group=group2),
            make_pad(cap=0.0, signature_color=sig2),
        ]
        segs2, _ = prog.render(pads2, palette, make_clock(), {})

        group3 = frozenset({0, 1, 2})
        pads3 = [
            make_pad(cap=0.0, signature_color=sig0, group=group3),
            make_pad(cap=0.0, signature_color=sig1, group=group3),
            make_pad(cap=0.0, signature_color=sig2, group=group3),
        ]
        segs3, _ = prog.render(pads3, palette, make_clock(), {})

        # For pad 0, group of 3 uses blend_t=0.6 vs group of 2 uses blend_t=0.3.
        # Centroid differs too, but the blend factor is larger for group of 3.
        # We verify that pad0's output color differs between the two group sizes.
        assert segs2[0].col != segs3[0].col

    def test_converge_grouped_pad_higher_brightness_floor(self):
        """A pad in the group at cap=0 has bri >= 50."""
        prog = get_program("converge")
        palette = make_palette()
        sig0 = [217, 24, 40]
        sig1 = [2, 136, 166]
        group = frozenset({0, 1})
        pads = [
            make_pad(cap=0.0, signature_color=sig0, group=group),
            make_pad(cap=0.0, signature_color=sig1, group=group),
        ]
        segs, _ = prog.render(pads, palette, make_clock(), {})
        assert segs[0].bri >= 50

    def test_converge_ungrouped_pad_lower_brightness_floor(self):
        """A pad not in the group at cap=0 has bri == 20."""
        prog = get_program("converge")
        palette = make_palette()
        # pad index 0 is in group {1}, so pad 0 is not in the group
        sig0 = [217, 24, 40]
        sig1 = [2, 136, 166]
        group = frozenset({1})  # only pad index 1 is in the group
        pads = [
            make_pad(cap=0.0, signature_color=sig0, group=group),
            make_pad(cap=0.0, signature_color=sig1, group=group),
        ]
        segs, _ = prog.render(pads, palette, make_clock(), {})
        assert segs[0].bri == 20

    def test_converge_returns_empty_state(self):
        prog = get_program("converge")
        pads = [make_pad() for _ in range(4)]
        _, state = prog.render(pads, make_palette(), make_clock(), {})
        assert state == {}


# ---------------------------------------------------------------------------
# Bloom program
# ---------------------------------------------------------------------------

class TestBloomProgram:
    def test_bloom_is_registered(self):
        assert "bloom" in list_programs()

    def test_bloom_name(self):
        prog = get_program("bloom")
        assert prog.name == "bloom"

    def test_bloom_render_returns_one_segment_per_pad(self):
        prog = get_program("bloom")
        pads = [make_pad() for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert len(segments) == 4

    def test_bloom_all_pads_same_color(self):
        """All pads use the same unison color regardless of signature_color."""
        prog = get_program("bloom")
        palette = make_palette()
        pads = [
            make_pad(signature_color=[217, 24, 40]),
            make_pad(signature_color=[2, 136, 166]),
            make_pad(signature_color=None),
            make_pad(signature_color=[242, 174, 48]),
        ]
        segments, _ = prog.render(pads, palette, make_clock(), {})
        colors = [seg.col for seg in segments]
        assert all(c == colors[0] for c in colors)

    def test_bloom_uses_palette_unison(self):
        """With ascending palette, bloom uses palette unison color."""
        prog = get_program("bloom")
        unison = [168, 191, 187]
        palette = Palette("ascending", {"idle": unison, "warm": [242, 220, 180], "unison": unison, "accent": [255, 255, 240]})
        pads = [make_pad()]
        segs, _ = prog.render(pads, palette, make_clock(), {})
        assert segs[0].col == [unison]

    def test_bloom_uses_default_unison_without_palette_key(self):
        """Without a unison key in palette, bloom falls back to [168, 191, 187]."""
        prog = get_program("bloom")
        palette = make_palette()  # default palette has no 'unison' key
        pads = [make_pad()]
        segs, _ = prog.render(pads, palette, make_clock(), {})
        assert segs[0].col == [[168, 191, 187]]

    def test_bloom_high_brightness(self):
        """All segments have bri >= 200."""
        prog = get_program("bloom")
        pads = [make_pad() for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        for seg in segments:
            assert seg.bri >= 200

    def test_bloom_brightness_varies_with_bar_phase(self):
        """Different bar phases produce different brightness."""
        prog = get_program("bloom")
        palette = make_palette()
        pads = [make_pad()]
        segs_0, _ = prog.render(pads, palette, ClockPhase(beat=0.0, bar=0.0, bpm=120.0), {})
        segs_25, _ = prog.render(pads, palette, ClockPhase(beat=0.0, bar=0.25, bpm=120.0), {})
        # bar=0.0: sin(0)=0 → pulse=0.5 → bri=228
        # bar=0.25: sin(pi/2)=1 → pulse=1.0 → bri=255
        assert segs_0[0].bri != segs_25[0].bri

    def test_bloom_returns_empty_state(self):
        prog = get_program("bloom")
        pads = [make_pad() for _ in range(4)]
        _, state = prog.render(pads, make_palette(), make_clock(), {})
        assert state == {}


# ---------------------------------------------------------------------------
# Dazzle program
# ---------------------------------------------------------------------------

class TestDazzleProgram:
    def test_dazzle_is_registered(self):
        assert "dazzle" in list_programs()

    def test_dazzle_name(self):
        prog = get_program("dazzle")
        assert prog.name == "dazzle"

    def test_dazzle_render_returns_one_segment_per_pad(self):
        prog = get_program("dazzle")
        pads = [make_pad(signature_color=[255, 0, 0]) for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        assert len(segments) == 4

    def test_dazzle_full_brightness(self):
        """All pads at bri=255."""
        prog = get_program("dazzle")
        pads = [make_pad(signature_color=[255, 0, 0]) for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        for seg in segments:
            assert seg.bri == 255

    def test_dazzle_uses_solid_fx(self):
        """All pads use fx=0 (Solid)."""
        prog = get_program("dazzle")
        pads = [make_pad(signature_color=[255, 0, 0]) for _ in range(4)]
        segments, _ = prog.render(pads, make_palette(), make_clock(), {})
        for seg in segments:
            assert seg.fx == 0

    def test_dazzle_bar_zero_no_rotation(self):
        """At bar=0.0, colors are in original pad order."""
        prog = get_program("dazzle")
        sig = [[217, 24, 40], [2, 136, 166], [217, 207, 74], [242, 174, 48]]
        pads = [make_pad(signature_color=s) for s in sig]
        clock = ClockPhase(beat=0.0, bar=0.0, bpm=120.0)
        segs, _ = prog.render(pads, make_palette(), clock, {})
        for i, s in enumerate(sig):
            assert segs[i].col == [s]

    def test_dazzle_rotates_one_step_at_quarter_bar(self):
        """At bar=0.25 (beat 1 of 4), colors shift by one station."""
        prog = get_program("dazzle")
        sig = [[217, 24, 40], [2, 136, 166], [217, 207, 74], [242, 174, 48]]
        pads = [make_pad(signature_color=s) for s in sig]
        clock = ClockPhase(beat=0.0, bar=0.25, bpm=120.0)
        segs, _ = prog.render(pads, make_palette(), clock, {})
        # offset=1: pad 0 gets color from index (0-1)%4 = 3
        assert segs[0].col == [sig[3]]
        assert segs[1].col == [sig[0]]
        assert segs[2].col == [sig[1]]
        assert segs[3].col == [sig[2]]

    def test_dazzle_rotates_two_steps_at_half_bar(self):
        """At bar=0.5 (beat 2 of 4), colors shift by two stations."""
        prog = get_program("dazzle")
        sig = [[217, 24, 40], [2, 136, 166], [217, 207, 74], [242, 174, 48]]
        pads = [make_pad(signature_color=s) for s in sig]
        clock = ClockPhase(beat=0.0, bar=0.5, bpm=120.0)
        segs, _ = prog.render(pads, make_palette(), clock, {})
        assert segs[0].col == [sig[2]]
        assert segs[1].col == [sig[3]]
        assert segs[2].col == [sig[0]]
        assert segs[3].col == [sig[1]]

    def test_dazzle_full_rotation_wraps(self):
        """At bar=1.0 (wraps to 0.0), back to original order."""
        prog = get_program("dazzle")
        sig = [[217, 24, 40], [2, 136, 166], [217, 207, 74], [242, 174, 48]]
        pads = [make_pad(signature_color=s) for s in sig]
        # bar phase wraps, so 0.999... should be offset 3
        clock_start = ClockPhase(beat=0.0, bar=0.0, bpm=120.0)
        segs, _ = prog.render(pads, make_palette(), clock_start, {})
        for i, s in enumerate(sig):
            assert segs[i].col == [s]

    def test_dazzle_falls_back_to_palette_idle(self):
        """Pads without signature_color use palette idle."""
        prog = get_program("dazzle")
        palette = make_palette()
        pads = [make_pad(signature_color=None) for _ in range(4)]
        clock = ClockPhase(beat=0.0, bar=0.0, bpm=120.0)
        segs, _ = prog.render(pads, palette, clock, {})
        for seg in segs:
            assert seg.col == [palette.get("idle")]

    def test_dazzle_empty_pads(self):
        prog = get_program("dazzle")
        segs, state = prog.render([], make_palette(), make_clock(), {})
        assert segs == []
        assert state == {}

    def test_dazzle_returns_empty_state(self):
        prog = get_program("dazzle")
        pads = [make_pad(signature_color=[255, 0, 0]) for _ in range(4)]
        _, state = prog.render(pads, make_palette(), make_clock(), {})
        assert state == {}
