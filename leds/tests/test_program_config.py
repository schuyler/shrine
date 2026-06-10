"""Tests for leds.program_config — hot-reloadable per-program LED parameters.

These tests are written RED: they import functions that do not yet exist.
All tests are expected to fail (ImportError) until the Green phase implements
leds.program_config.
"""

import threading

import pytest

from leds.program_config import (  # noqa: E402
    get_program_params,
    resolve_ix,
    resolve_sx,
    set_program_params,
)

# ---------------------------------------------------------------------------
# Fixture: reset global state before and after every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_params():
    set_program_params({})
    yield
    set_program_params({})


# ---------------------------------------------------------------------------
# Defaults for unknown programs
# ---------------------------------------------------------------------------


class TestGetProgramParamsDefaults:
    def test_unknown_program_returns_sx_base_128(self):
        params = get_program_params("nonexistent")
        assert params["sx"]["base"] == 128

    def test_unknown_program_returns_sx_scale_0(self):
        params = get_program_params("nonexistent")
        assert params["sx"]["scale"] == 0.0

    def test_unknown_program_returns_ix_base_128(self):
        params = get_program_params("nonexistent")
        assert params["ix"]["base"] == 128

    def test_unknown_program_returns_ix_scale_0(self):
        params = get_program_params("nonexistent")
        assert params["ix"]["scale"] == 0.0


# ---------------------------------------------------------------------------
# Set / get round-trip
# ---------------------------------------------------------------------------


class TestSetGetRoundTrip:
    def test_set_then_get_returns_set_values(self):
        set_program_params({
            "breathe": {
                "sx": {"base": 50, "scale": 1.0},
                "ix": {"base": 75, "scale": 0.5},
            }
        })
        params = get_program_params("breathe")
        assert params["sx"]["base"] == 50
        assert params["sx"]["scale"] == 1.0
        assert params["ix"]["base"] == 75
        assert params["ix"]["scale"] == 0.5

    def test_second_set_replaces_first(self):
        set_program_params({
            "breathe": {"sx": {"base": 10, "scale": 0.0}, "ix": {"base": 20, "scale": 0.0}}
        })
        set_program_params({
            "breathe": {"sx": {"base": 99, "scale": 0.1}, "ix": {"base": 88, "scale": 0.2}}
        })
        params = get_program_params("breathe")
        assert params["sx"]["base"] == 99
        assert params["sx"]["scale"] == 0.1
        assert params["ix"]["base"] == 88
        assert params["ix"]["scale"] == 0.2


# ---------------------------------------------------------------------------
# Partial overrides / defaults merging
# ---------------------------------------------------------------------------


class TestPartialOverrides:
    def test_only_sx_set_ix_falls_back_to_defaults(self):
        set_program_params({
            "breathe": {"sx": {"base": 64, "scale": 0.5}}
        })
        params = get_program_params("breathe")
        assert params["sx"]["base"] == 64
        assert params["sx"]["scale"] == 0.5
        # ix must come from defaults
        assert params["ix"]["base"] == 128
        assert params["ix"]["scale"] == 0.0

    def test_only_ix_set_sx_falls_back_to_defaults(self):
        set_program_params({
            "breathe": {"ix": {"base": 200, "scale": 0.3}}
        })
        params = get_program_params("breathe")
        assert params["ix"]["base"] == 200
        assert params["ix"]["scale"] == 0.3
        # sx must come from defaults
        assert params["sx"]["base"] == 128
        assert params["sx"]["scale"] == 0.0

    def test_partial_sx_only_base_scale_defaults(self):
        set_program_params({
            "breathe": {"sx": {"base": 42}}
        })
        params = get_program_params("breathe")
        assert params["sx"]["base"] == 42
        assert params["sx"]["scale"] == 0.0


# ---------------------------------------------------------------------------
# resolve_sx
# ---------------------------------------------------------------------------


class TestResolveSx:
    def test_zero_scale_returns_base(self):
        params = {"sx": {"base": 100, "scale": 0.0}, "ix": {"base": 128, "scale": 0.0}}
        assert resolve_sx(params, bpm=120.0) == 100

    def test_nonzero_scale_adds_bpm_contribution(self):
        # base=100, scale=0.5, bpm=120 → 100 + 0.5*120 = 160
        params = {"sx": {"base": 100, "scale": 0.5}, "ix": {"base": 128, "scale": 0.0}}
        result = resolve_sx(params, bpm=120.0)
        assert result == 160
        assert isinstance(result, int)

    def test_clamps_below_zero(self):
        # base=-50, scale=0, bpm=0 → clamp to 0
        params = {"sx": {"base": -50, "scale": 0.0}, "ix": {"base": 128, "scale": 0.0}}
        assert resolve_sx(params, bpm=0.0) == 0

    def test_clamps_above_255(self):
        # base=200, scale=1.0, bpm=200 → 400 → clamp to 255
        params = {"sx": {"base": 200, "scale": 1.0}, "ix": {"base": 128, "scale": 0.0}}
        assert resolve_sx(params, bpm=200.0) == 255


# ---------------------------------------------------------------------------
# resolve_ix
# ---------------------------------------------------------------------------


class TestResolveIx:
    def test_zero_scale_returns_base(self):
        params = {"sx": {"base": 128, "scale": 0.0}, "ix": {"base": 100, "scale": 0.0}}
        assert resolve_ix(params, bpm=120.0) == 100

    def test_nonzero_scale_adds_bpm_contribution(self):
        # base=100, scale=0.5, bpm=120 → 160
        params = {"sx": {"base": 128, "scale": 0.0}, "ix": {"base": 100, "scale": 0.5}}
        result = resolve_ix(params, bpm=120.0)
        assert result == 160
        assert isinstance(result, int)

    def test_clamps_below_zero(self):
        # base=-50, scale=0, bpm=0 → clamp to 0
        params = {"sx": {"base": 128, "scale": 0.0}, "ix": {"base": -50, "scale": 0.0}}
        assert resolve_ix(params, bpm=0.0) == 0

    def test_clamps_above_255(self):
        # base=200, scale=1.0, bpm=200 → 400 → clamp to 255
        params = {"sx": {"base": 128, "scale": 0.0}, "ix": {"base": 200, "scale": 1.0}}
        assert resolve_ix(params, bpm=200.0) == 255


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_reads_during_writes_do_not_raise(self):
        errors = []

        def writer():
            for _ in range(50):
                set_program_params({"breathe": {"sx": {"base": 64, "scale": 0.0}}})

        def reader():
            for _ in range(50):
                try:
                    get_program_params("breathe")
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread-safety errors: {errors}"
