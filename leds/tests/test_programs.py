import pytest

from leds.programs import Program, SegmentParams, get_program, list_programs, register
from leds.pad_state import PadSnapshot
from leds.clock import ClockPhase
from leds.palettes import Palette


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pad(cap=0.0, heartbeat=0.0, flux=0.0, signature_color=None):
    return PadSnapshot(cap=cap, heartbeat=heartbeat, flux=flux, signature_color=signature_color)


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
