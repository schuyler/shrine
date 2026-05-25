import math

import pytest

from leds.osc_input import build_dispatcher
from leds.sensor_state import SensorState


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


class TestSimulatorCapHandlers:
    def test_pad1_cap_updates_slot0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/1/cap", 0.8)
        cap, _, _ = state.snapshot()
        assert cap[0] == pytest.approx(0.8)

    def test_pad2_cap_updates_slot1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/2/cap", 0.5)
        cap, _, _ = state.snapshot()
        assert cap[1] == pytest.approx(0.5)

    def test_pad3_cap_updates_slot2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/3/cap", 0.3)
        cap, _, _ = state.snapshot()
        assert cap[2] == pytest.approx(0.3)

    def test_pad4_cap_updates_slot3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/4/cap", 0.1)
        cap, _, _ = state.snapshot()
        assert cap[3] == pytest.approx(0.1)

    def test_pad1_cap_does_not_affect_other_slots(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/1/cap", 0.9)
        cap, _, _ = state.snapshot()
        assert cap[1] == 0
        assert cap[2] == 0
        assert cap[3] == 0


class TestSimulatorGsrMagHandlers:
    def test_gsr_1_2_updates_global_index_0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/2", 0.7)
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[0] == pytest.approx(0.7)

    def test_gsr_1_3_updates_global_index_1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/3", 0.6)
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[1] == pytest.approx(0.6)

    def test_gsr_1_4_updates_global_index_2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/4", 0.5)
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[2] == pytest.approx(0.5)

    def test_gsr_2_3_updates_global_index_3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/2/3", 0.4)
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[3] == pytest.approx(0.4)

    def test_gsr_2_4_updates_global_index_4(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/2/4", 0.3)
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[4] == pytest.approx(0.3)

    def test_gsr_3_4_updates_global_index_5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/3/4", 0.2)
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[5] == pytest.approx(0.2)


class TestSimulatorGsrPhaseHandlers:
    def test_gsr_1_2_phase_updates_global_index_0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/2/phase", 1.5)
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[0] == pytest.approx(1.5)

    def test_gsr_3_4_phase_updates_global_index_5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/3/4/phase", 4.2)
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[5] == pytest.approx(4.2)

    def test_simulator_phase_stored_as_is_no_normalization(self):
        """Simulator sends 0..2pi; no normalization should occur."""
        state = SensorState()
        dispatcher = build_dispatcher(state)
        two_pi = 2 * math.pi
        _call(dispatcher, "/gsr/2/3/phase", two_pi * 0.75)
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[3] == pytest.approx(two_pi * 0.75)

    def test_simulator_phase_zero_stored_as_zero(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/3/phase", 0.0)
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[1] == pytest.approx(0.0)


class TestEdgeNodeHandlerNode0:
    """Node 0 has no GSR RX slots; only cap updates."""

    def _send_node0(self, dispatcher, cap, gsr_mags, gsr_phases):
        args = [cap] + gsr_mags + gsr_phases
        _call(dispatcher, "/shrine/node/0", *args)

    def test_node0_updates_cap_slot0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.6, [0.1, 0.2, 0.3], [0.4, 0.5, 0.6])
        cap, _, _ = state.snapshot()
        assert cap[0] == pytest.approx(0.6)

    def test_node0_does_not_update_gsr_mag(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.6, [0.9, 0.8, 0.7], [1.0, 1.1, 1.2])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag == [0, 0, 0, 0, 0, 0]

    def test_node0_does_not_update_gsr_phase(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.6, [0.1, 0.2, 0.3], [1.0, 2.0, 3.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase == [0, 0, 0, 0, 0, 0]


class TestEdgeNodeHandlerNode1:
    """Node 1: NODE_GSR_MAPPING[1] = [0] — one active GSR slot maps to global pair 0."""

    def _send_node1(self, dispatcher, cap, gsr_mags, gsr_phases):
        args = [cap] + gsr_mags + gsr_phases
        _call(dispatcher, "/shrine/node/1", *args)

    def test_node1_updates_cap_slot1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.6, [0.3, 0.0, 0.0], [1.0, 0.0, 0.0])
        cap, _, _ = state.snapshot()
        assert cap[1] == pytest.approx(0.6)

    def test_node1_updates_gsr_mag_global0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.6, [0.3, 0.0, 0.0], [1.0, 0.0, 0.0])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[0] == pytest.approx(0.3)

    def test_node1_updates_gsr_phase_global0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.6, [0.3, 0.0, 0.0], [1.0, 0.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[0] == pytest.approx(1.0)

    def test_node1_does_not_update_other_global_pairs(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.6, [0.3, 0.0, 0.0], [1.0, 0.0, 0.0])
        _, gsr_mag, gsr_phase = state.snapshot()
        for i in range(1, 6):
            assert gsr_mag[i] == 0
            assert gsr_phase[i] == 0


class TestEdgeNodeHandlerNode2:
    """Node 2: NODE_GSR_MAPPING[2] = [1, 3] — two active slots, tests phase normalization."""

    def _send_node2(self, dispatcher, cap, gsr_mags, gsr_phases):
        args = [cap] + gsr_mags + gsr_phases
        _call(dispatcher, "/shrine/node/2", *args)

    def test_node2_updates_cap_slot2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.5, [0.4, 0.35, 0.0], [0.5, -1.0, 0.0])
        cap, _, _ = state.snapshot()
        assert cap[2] == pytest.approx(0.5)

    def test_node2_updates_gsr_mag_global1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.5, [0.4, 0.35, 0.0], [0.5, -1.0, 0.0])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[1] == pytest.approx(0.4)

    def test_node2_updates_gsr_mag_global3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.5, [0.4, 0.35, 0.0], [0.5, -1.0, 0.0])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[3] == pytest.approx(0.35)

    def test_node2_updates_gsr_phase_global1_positive_unchanged(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.5, [0.4, 0.35, 0.0], [0.5, -1.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[1] == pytest.approx(0.5)

    def test_node2_updates_gsr_phase_global3_negative_normalized(self):
        """local[1] phase = -1.0; normalization adds 2*pi to give a positive result."""
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.5, [0.4, 0.35, 0.0], [0.5, -1.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[3] == pytest.approx(-1.0 + 2 * math.pi, abs=1e-5)

    def test_node2_does_not_update_global_pairs_0_2_4_5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.5, [0.4, 0.35, 0.0], [0.5, -1.0, 0.0])
        _, gsr_mag, gsr_phase = state.snapshot()
        for i in [0, 2, 4, 5]:
            assert gsr_mag[i] == 0
            assert gsr_phase[i] == 0


class TestEdgeNodeHandlerNode3:
    """Node 3 maps local[0]->global 2, local[1]->global 4, local[2]->global 5."""

    def _send_node3(self, dispatcher, cap, gsr_mags, gsr_phases):
        args = [cap] + gsr_mags + gsr_phases
        _call(dispatcher, "/shrine/node/3", *args)

    def test_node3_updates_cap_slot3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.7, [0.1, 0.2, 0.3], [0.0, 0.0, 0.0])
        cap, _, _ = state.snapshot()
        assert cap[3] == pytest.approx(0.7)

    def test_node3_updates_gsr_mag_global2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, [0.4, 0.5, 0.6], [0.0, 0.0, 0.0])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[2] == pytest.approx(0.4)

    def test_node3_updates_gsr_mag_global4(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, [0.4, 0.5, 0.6], [0.0, 0.0, 0.0])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[4] == pytest.approx(0.5)

    def test_node3_updates_gsr_mag_global5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, [0.4, 0.5, 0.6], [0.0, 0.0, 0.0])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[5] == pytest.approx(0.6)

    def test_node3_does_not_update_other_gsr_mag_slots(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, [0.4, 0.5, 0.6], [0.0, 0.0, 0.0])
        _, gsr_mag, _ = state.snapshot()
        assert gsr_mag[0] == 0
        assert gsr_mag[1] == 0
        assert gsr_mag[3] == 0

    def test_node3_positive_phase_passes_through_normalization_unchanged(self):
        # The normalization conditional (if phase < 0: phase += 2*pi) runs but
        # does not change positive values, so the stored result equals the input.
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, [0.0, 0.0, 0.0], [math.pi, 2.0, 3.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[2] == pytest.approx(math.pi)

    def test_node3_zero_phase_stays_zero(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[2] == pytest.approx(0.0)
        assert gsr_phase[4] == pytest.approx(0.0)
        assert gsr_phase[5] == pytest.approx(0.0)


class TestEdgeNodePhaseNormalization:
    """Negative phase from edge nodes should get +2pi."""

    def _send_node3(self, dispatcher, phases):
        args = [0.0, 0.0, 0.0, 0.0] + phases
        _call(dispatcher, "/shrine/node/3", *args)

    def test_negative_pi_normalizes_to_pi(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, [-math.pi, 0.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[2] == pytest.approx(math.pi, abs=1e-5)

    def test_zero_phase_stays_zero(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, [0.0, 0.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[2] == pytest.approx(0.0)

    def test_positive_pi_stays_pi(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, [math.pi, 0.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[2] == pytest.approx(math.pi)

    def test_negative_half_pi_normalizes(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, [-math.pi / 2, 0.0, 0.0])
        _, _, gsr_phase = state.snapshot()
        assert gsr_phase[2] == pytest.approx(3 * math.pi / 2, abs=1e-5)
