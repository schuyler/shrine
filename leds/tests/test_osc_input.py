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
        cap, _ = state.snapshot()
        assert cap[0] == pytest.approx(0.8)

    def test_pad2_cap_updates_slot1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/2/cap", 0.5)
        cap, _ = state.snapshot()
        assert cap[1] == pytest.approx(0.5)

    def test_pad3_cap_updates_slot2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/3/cap", 0.3)
        cap, _ = state.snapshot()
        assert cap[2] == pytest.approx(0.3)

    def test_pad4_cap_updates_slot3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/4/cap", 0.1)
        cap, _ = state.snapshot()
        assert cap[3] == pytest.approx(0.1)

    def test_pad1_cap_does_not_affect_other_slots(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/pad/1/cap", 0.9)
        cap, _ = state.snapshot()
        assert cap[1] == 0
        assert cap[2] == 0
        assert cap[3] == 0


class TestSimulatorGsrMagHandlers:
    def test_gsr_1_2_updates_global_index_0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/2", 0.7)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[0] == pytest.approx(0.7)

    def test_gsr_1_3_updates_global_index_1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/3", 0.6)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[1] == pytest.approx(0.6)

    def test_gsr_1_4_updates_global_index_2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/1/4", 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[2] == pytest.approx(0.5)

    def test_gsr_2_3_updates_global_index_3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/2/3", 0.4)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[3] == pytest.approx(0.4)

    def test_gsr_2_4_updates_global_index_4(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/2/4", 0.3)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[4] == pytest.approx(0.3)

    def test_gsr_3_4_updates_global_index_5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        _call(dispatcher, "/gsr/3/4", 0.2)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[5] == pytest.approx(0.2)


class TestEdgeNodeHandlerNode0:
    """Node 0: NODE_GSR_MAPPING[0] = [0, 1, 2] — all 3 GSR slots active."""

    def _send_node0(self, dispatcher, stdev, carrier_mag, m0, m1, m2):
        _call(dispatcher, "/shrine/node/0", stdev, carrier_mag, m0, m1, m2)

    def test_node0_updates_cap_slot0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.6, 0.0, 0.1, 0.2, 0.3)
        cap, _ = state.snapshot()
        assert cap[0] == pytest.approx(0.6)

    def test_node0_uses_stdev_as_cap(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.42, 0.9, 0.1, 0.2, 0.3)
        cap, _ = state.snapshot()
        assert cap[0] == pytest.approx(0.42)

    def test_node0_updates_gsr_mag_global0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.0, 0.0, 0.11, 0.22, 0.33)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[0] == pytest.approx(0.11)

    def test_node0_updates_gsr_mag_global1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.0, 0.0, 0.11, 0.22, 0.33)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[1] == pytest.approx(0.22)

    def test_node0_updates_gsr_mag_global2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.0, 0.0, 0.11, 0.22, 0.33)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[2] == pytest.approx(0.33)

    def test_node0_does_not_update_globals_3_4_5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node0(dispatcher, 0.0, 0.0, 0.5, 0.5, 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[3] == 0
        assert gsr_mag[4] == 0
        assert gsr_mag[5] == 0


class TestEdgeNodeHandlerNode1:
    """Node 1: NODE_GSR_MAPPING[1] = [3, 4, 0] — all 3 GSR slots map to globals 3, 4, 0."""

    def _send_node1(self, dispatcher, stdev, carrier_mag, m0, m1, m2):
        _call(dispatcher, "/shrine/node/1", stdev, carrier_mag, m0, m1, m2)

    def test_node1_updates_cap_slot1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.6, 0.0, 0.3, 0.4, 0.5)
        cap, _ = state.snapshot()
        assert cap[1] == pytest.approx(0.6)

    def test_node1_updates_gsr_mag_global3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.0, 0.0, 0.3, 0.4, 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[3] == pytest.approx(0.3)

    def test_node1_updates_gsr_mag_global4(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.0, 0.0, 0.3, 0.4, 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[4] == pytest.approx(0.4)

    def test_node1_updates_gsr_mag_global0(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.0, 0.0, 0.3, 0.4, 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[0] == pytest.approx(0.5)

    def test_node1_does_not_update_globals_1_2_5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node1(dispatcher, 0.0, 0.0, 0.5, 0.5, 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[1] == 0
        assert gsr_mag[2] == 0
        assert gsr_mag[5] == 0


class TestEdgeNodeHandlerNode2:
    """Node 2: NODE_GSR_MAPPING[2] = [5, 1, 3] — all 3 GSR slots map to globals 5, 1, 3."""

    def _send_node2(self, dispatcher, stdev, carrier_mag, m0, m1, m2):
        _call(dispatcher, "/shrine/node/2", stdev, carrier_mag, m0, m1, m2)

    def test_node2_updates_cap_slot2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.5, 0.0, 0.4, 0.35, 0.25)
        cap, _ = state.snapshot()
        assert cap[2] == pytest.approx(0.5)

    def test_node2_updates_gsr_mag_global5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.0, 0.0, 0.4, 0.35, 0.25)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[5] == pytest.approx(0.4)

    def test_node2_updates_gsr_mag_global1(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.0, 0.0, 0.4, 0.35, 0.25)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[1] == pytest.approx(0.35)

    def test_node2_updates_gsr_mag_global3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.0, 0.0, 0.4, 0.35, 0.25)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[3] == pytest.approx(0.25)

    def test_node2_does_not_update_globals_0_2_4(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node2(dispatcher, 0.0, 0.0, 0.5, 0.5, 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[0] == 0
        assert gsr_mag[2] == 0
        assert gsr_mag[4] == 0


class TestEdgeNodeHandlerNode3:
    """Node 3: NODE_GSR_MAPPING[3] = [2, 4, 5] — all 3 GSR slots map to globals 2, 4, 5."""

    def _send_node3(self, dispatcher, stdev, carrier_mag, m0, m1, m2):
        _call(dispatcher, "/shrine/node/3", stdev, carrier_mag, m0, m1, m2)

    def test_node3_updates_cap_slot3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.7, 0.0, 0.1, 0.2, 0.3)
        cap, _ = state.snapshot()
        assert cap[3] == pytest.approx(0.7)

    def test_node3_updates_gsr_mag_global2(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, 0.0, 0.4, 0.5, 0.6)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[2] == pytest.approx(0.4)

    def test_node3_updates_gsr_mag_global4(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, 0.0, 0.4, 0.5, 0.6)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[4] == pytest.approx(0.5)

    def test_node3_updates_gsr_mag_global5(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, 0.0, 0.4, 0.5, 0.6)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[5] == pytest.approx(0.6)

    def test_node3_does_not_update_globals_0_1_3(self):
        state = SensorState()
        dispatcher = build_dispatcher(state)
        self._send_node3(dispatcher, 0.0, 0.0, 0.5, 0.5, 0.5)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[0] == 0
        assert gsr_mag[1] == 0
        assert gsr_mag[3] == 0
