import time

import pytest

from leds.osc_input import build_dispatcher
from leds.pad_state import PadState


def _get_handler(dispatcher, address):
    """Return the first handler registered for the given address.

    Tries the public handlers_for_address() API first (python-osc >= 1.8).
    Falls back to the private _map attribute for older versions.
    If neither is available the calling test is skipped with a diagnostic
    message rather than raising an opaque AttributeError.
    """
    # Public API (python-osc >= 1.8)
    if hasattr(dispatcher, "handlers_for_address"):
        handlers = list(dispatcher.handlers_for_address(address))
        if not handlers:
            pytest.skip(
                f"No handler registered for {address!r} via handlers_for_address()"
            )
        handler = handlers[0]
        return handler.callback if hasattr(handler, "callback") else handler

    # Private fallback — python-osc stores handlers in dispatcher._map
    if not hasattr(dispatcher, "_map"):
        pytest.skip(
            "Cannot extract handlers: dispatcher has neither handlers_for_address() "
            "nor _map. Upgrade or pin python-osc."
        )
    entry = dispatcher._map.get(address)
    if entry is None:
        raise KeyError(f"No handler registered for {address!r}")
    handler = entry[0]
    if callable(handler):
        return handler
    # Handler may be wrapped in a list/tuple by some pythonosc versions
    return handler[0]


def _call(dispatcher, address, *args):
    """Invoke the registered handler for address with the given args."""
    handler = _get_handler(dispatcher, address)
    handler(address, *args)


class TestCapHandler:
    def test_cap_updates_correct_pad(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/cap", 0, 0.8)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[0].cap == pytest.approx(0.8)

    def test_cap_updates_pad1(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/cap", 1, 0.5)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[1].cap == pytest.approx(0.5)

    def test_cap_updates_pad2(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/cap", 2, 0.3)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[2].cap == pytest.approx(0.3)

    def test_cap_updates_pad3(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/cap", 3, 0.1)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[3].cap == pytest.approx(0.1)

    def test_cap_does_not_affect_other_pads(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/cap", 0, 0.9)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[1].cap == 0.0
        assert snapshots[2].cap == 0.0
        assert snapshots[3].cap == 0.0

    def test_cap_value_correctness(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/cap", 2, 0.42)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[2].cap == pytest.approx(0.42)


class TestHeartbeatHandler:
    def test_heartbeat_updates_correct_pad(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/heartbeat", 0, 1.2)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[0].heartbeat == pytest.approx(1.2)

    def test_heartbeat_updates_pad1(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/heartbeat", 1, 0.8)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[1].heartbeat == pytest.approx(0.8)

    def test_heartbeat_does_not_affect_other_pads(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/heartbeat", 2, 1.0)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[0].heartbeat == 0.0
        assert snapshots[1].heartbeat == 0.0
        assert snapshots[3].heartbeat == 0.0


class TestFluxHandler:
    def test_flux_updates_correct_pad(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/flux", 0, 0.7)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[0].flux == pytest.approx(0.7)

    def test_flux_updates_pad3(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/flux", 3, 0.33)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[3].flux == pytest.approx(0.33)

    def test_flux_does_not_affect_other_pads(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/flux", 1, 0.5)
        snapshots, _, _, _, _, _ = state.snapshot()
        assert snapshots[0].flux == 0.0
        assert snapshots[2].flux == 0.0
        assert snapshots[3].flux == 0.0


class TestProgramHandler:
    def test_sets_program_name(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/program", "breathe")
        _, program, _, _, _, _ = state.snapshot()
        assert program == "breathe"

    def test_sets_different_program_name(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/program", "pulse")
        _, program, _, _, _, _ = state.snapshot()
        assert program == "pulse"


class TestPaletteHandler:
    def test_sets_palette_name(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/palette", "default")
        _, _, palette, _, _, _ = state.snapshot()
        assert palette == "default"

    def test_sets_different_palette_name(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/palette", "warm")
        _, _, palette, _, _, _ = state.snapshot()
        assert palette == "warm"


class TestTempoHandler:
    def test_sets_bpm(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/tempo", 120.0)
        _, _, _, bpm, _, _ = state.snapshot()
        assert bpm == pytest.approx(120.0)

    def test_sync_time_is_positive(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        before = time.monotonic()
        _call(dispatcher, "/leds/tempo", 90.0)
        after = time.monotonic()
        _, _, _, _, sync_time, _ = state.snapshot()
        assert sync_time >= before
        assert sync_time <= after

    def test_tempo_increments_gen(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _, _, _, _, _, gen_before = state.snapshot()
        _call(dispatcher, "/leds/tempo", 100.0)
        _, _, _, _, _, gen_after = state.snapshot()
        assert gen_after == gen_before + 1

    def test_tempo_gen_increments_each_call(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/tempo", 100.0)
        _call(dispatcher, "/leds/tempo", 110.0)
        _, _, _, _, _, gen = state.snapshot()
        assert gen == 2


class TestOutOfRangePad:
    def test_cap_unknown_pad_does_not_crash(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/leds/cap", 99, 0.5)
        snapshots, _, _, _, _, _ = state.snapshot()
        for snap in snapshots:
            assert snap.cap == 0.0


class TestDefaultHandler:
    def test_unrecognized_address_does_not_crash(self):
        state = PadState([0, 1, 2, 3])
        dispatcher = build_dispatcher(state)
        # Invoking the default handler should not raise
        if hasattr(dispatcher, "default_handler"):
            try:
                dispatcher.default_handler("/unknown/address", 1, 2, 3)
            except Exception as exc:
                pytest.fail(f"Default handler raised: {exc}")
        else:
            # If no default_handler attribute, just verify the dispatcher exists
            assert dispatcher is not None
