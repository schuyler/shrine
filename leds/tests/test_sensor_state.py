"""Tests for leds.sensor_state."""

import pytest

from leds.sensor_state import (
    GSR_PAIRS,
    NODE_GSR_MAPPING,
    SensorState,
    SensorSnapshot,
    _largest_component,
)

_CFG = {
    "cap_on_threshold": 0.6,
    "cap_off_threshold": 0.4,
    "cap_hold_on": 0.3,
    "cap_hold_off": 0.5,
    "gsr_on_threshold": 0.4,
    "gsr_off_threshold": 0.25,
    "gsr_hold_on": 0.5,
    "gsr_hold_off": 1.0,
    "confirm_hold": 5.0,
}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_gsr_pairs_length(self):
        assert len(GSR_PAIRS) == 6

    def test_gsr_pairs_zero_indexed(self):
        for a, b in GSR_PAIRS:
            assert a >= 0
            assert b >= 0
            assert a < b

    def test_node_gsr_mapping_shape(self):
        assert len(NODE_GSR_MAPPING) == 4
        for row in NODE_GSR_MAPPING:
            assert len(row) == 3

    def test_node_gsr_mapping_valid_indices(self):
        for row in NODE_GSR_MAPPING:
            for idx in row:
                assert 0 <= idx < 6

    def test_each_pair_covered_twice(self):
        from collections import Counter
        counts = Counter(idx for row in NODE_GSR_MAPPING for idx in row)
        for pair_idx in range(6):
            assert counts[pair_idx] == 2, f"pair {pair_idx} seen {counts[pair_idx]} times"


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_snapshot_initially_nothing_engaged(self):
        s = SensorState(_CFG)
        snap = s.snapshot()
        assert snap.engaged == frozenset()

    def test_snapshot_initially_no_edges(self):
        s = SensorState(_CFG)
        snap = s.snapshot()
        assert snap.edges == frozenset()

    def test_snapshot_initially_empty_group(self):
        s = SensorState(_CFG)
        snap = s.snapshot()
        assert snap.group_members == frozenset()

    def test_snapshot_raw_cap_all_zero(self):
        s = SensorState(_CFG)
        snap = s.snapshot()
        assert all(v == pytest.approx(0.0) for v in snap.raw_cap)

    def test_snapshot_raw_gsr_all_zero(self):
        s = SensorState(_CFG)
        snap = s.snapshot()
        assert all(v == pytest.approx(0.0) for v in snap.raw_gsr)


# ---------------------------------------------------------------------------
# Schmitt trigger — cap
# ---------------------------------------------------------------------------

class TestCapSchmitt:
    def test_below_threshold_not_engaged_after_tick(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.5, 0.0, 0.0, 0.0, 0.0)
        s.tick(1.0)
        assert 0 not in s.snapshot().engaged

    def test_above_threshold_not_engaged_before_hold(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.1)
        assert 0 not in s.snapshot().engaged

    def test_engaged_after_hold_on(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        assert 0 in s.snapshot().engaged

    def test_disengages_after_drop_and_hold_off(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        s.update_node(0, 0.2, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.5)
        assert 0 not in s.snapshot().engaged

    def test_does_not_disengage_before_hold_off(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        s.update_node(0, 0.2, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        assert 0 in s.snapshot().engaged

    def test_pending_resets_on_signal_recovery(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        # drop briefly then recover — hold_off timer should reset
        s.update_node(0, 0.2, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        s.update_node(0, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        assert 0 in s.snapshot().engaged

    def test_multiple_pads_independent(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.update_node(1, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        snap = s.snapshot()
        assert 0 in snap.engaged
        assert 1 in snap.engaged
        assert 2 not in snap.engaged
        assert 3 not in snap.engaged

    def test_carrier_mag_not_stored(self):
        s = SensorState(_CFG)
        s.update_node(0, 0.0, 999.0, 0.0, 0.0, 0.0)
        s.tick(0.3)
        snap = s.snapshot()
        assert snap.raw_cap[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Schmitt trigger — GSR / edges
# ---------------------------------------------------------------------------

class TestGsrSchmitt:
    def _engage_pads(self, s, *pads):
        for p in pads:
            s.update_node(p, 0.8, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.3)

    def test_edge_requires_both_pads_engaged(self):
        s = SensorState(_CFG)
        self._engage_pads(s, 0)
        # Only pad 0 engaged; gsr value high
        s.update_node(0, 0.8, 0.0, 0.8, 0.8, 0.8)
        s.tick(0.5)
        assert s.snapshot().edges == frozenset()

    def test_edge_forms_when_both_engaged_and_gsr_above_threshold(self):
        s = SensorState(_CFG)
        self._engage_pads(s, 0, 1)
        # NODE_GSR_MAPPING[0][0] = 0 → GSR_PAIRS[0] = (0,1)
        s.update_node(0, 0.8, 0.0, 0.8, 0.0, 0.0)
        s.tick(0.5)
        assert (0, 1) in s.snapshot().edges

    def test_edge_not_formed_before_hold_on(self):
        s = SensorState(_CFG)
        self._engage_pads(s, 0, 1)
        s.update_node(0, 0.8, 0.0, 0.8, 0.0, 0.0)
        s.tick(0.2)
        assert (0, 1) not in s.snapshot().edges

    def test_edge_drops_when_pad_disengages(self):
        s = SensorState(_CFG)
        self._engage_pads(s, 0, 1)
        s.update_node(0, 0.8, 0.0, 0.8, 0.0, 0.0)
        s.tick(0.5)
        assert (0, 1) in s.snapshot().edges
        # Remove pad 1
        s.update_node(1, 0.1, 0.0, 0.0, 0.0, 0.0)
        s.tick(0.5)
        assert (0, 1) not in s.snapshot().edges


# ---------------------------------------------------------------------------
# GSR raw value routing
# ---------------------------------------------------------------------------

class TestGsrRouting:
    def test_update_node_routes_gsr_to_correct_pair(self):
        s = SensorState(_CFG)
        # NODE_GSR_MAPPING[2][0] = 5 → GSR_PAIRS[5] = (2,3)
        s.update_node(2, 0.0, 0.0, 0.7, 0.0, 0.0)
        snap = s.snapshot()
        assert snap.raw_gsr[5] == pytest.approx(0.7)

    def test_later_write_wins_for_same_pair(self):
        s = SensorState(_CFG)
        # Both node 0 slot 0 and node 1 slot 2 map to pair 0 (0,1)
        s.update_node(0, 0.0, 0.0, 0.3, 0.0, 0.0)
        s.update_node(1, 0.0, 0.0, 0.0, 0.0, 0.7)
        snap = s.snapshot()
        assert snap.raw_gsr[0] == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Connected components
# ---------------------------------------------------------------------------

class TestLargestComponent:
    def test_empty_engaged_returns_empty(self):
        assert _largest_component(frozenset(), frozenset()) == frozenset()

    def test_single_pad_no_edges(self):
        assert _largest_component(frozenset({0}), frozenset()) == frozenset({0})

    def test_two_pads_connected(self):
        result = _largest_component(frozenset({0, 1}), frozenset({(0, 1)}))
        assert result == frozenset({0, 1})

    def test_chain_of_three(self):
        result = _largest_component(
            frozenset({0, 1, 2}),
            frozenset({(0, 1), (1, 2)}),
        )
        assert result == frozenset({0, 1, 2})

    def test_disjoint_groups_returns_largest(self):
        result = _largest_component(
            frozenset({0, 1, 2, 3}),
            frozenset({(0, 1), (0, 2)}),
        )
        # 0,1,2 are one component; 3 is isolated
        assert result == frozenset({0, 1, 2})

    def test_all_four_connected(self):
        result = _largest_component(
            frozenset({0, 1, 2, 3}),
            frozenset({(0, 1), (1, 2), (2, 3)}),
        )
        assert result == frozenset({0, 1, 2, 3})

    def test_edge_to_absent_pad_ignored(self):
        # pad 2 not in engaged
        result = _largest_component(
            frozenset({0, 1}),
            frozenset({(0, 1), (1, 2)}),
        )
        assert result == frozenset({0, 1})


# ---------------------------------------------------------------------------
# Snapshot immutability
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_snapshot_is_frozen(self):
        s = SensorState(_CFG)
        snap = s.snapshot()
        assert isinstance(snap, SensorSnapshot)
        with pytest.raises((AttributeError, TypeError)):
            snap.engaged = frozenset({0})  # type: ignore[misc]

    def test_raw_cap_length(self):
        s = SensorState(_CFG)
        assert len(s.snapshot().raw_cap) == 4

    def test_raw_gsr_length(self):
        s = SensorState(_CFG)
        assert len(s.snapshot().raw_gsr) == 6
