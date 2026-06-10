"""Tests for the manual sensor simulator's UI-independent state model."""

import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, _HERE)                       # for `import manual`/`generator`
sys.path.insert(0, os.path.dirname(_HERE))      # repo root, for `import leds`

from leds.sensor_state import GSR_PAIRS, NODE_GSR_MAPPING

from manual import NUM_NODES, ManualState


def _gsr(args):
    """The three GSR floats of a node payload (after stdev, carrier)."""
    return args[2:]


def _slot_of(node, pair_idx):
    """Which GSR slot of `node` reports `pair_idx` (or None)."""
    mapping = NODE_GSR_MAPPING[node]
    return mapping.index(pair_idx) if pair_idx in mapping else None


def test_payload_shape_matches_firmware():
    state = ManualState(smoothing=False)
    state.update()
    sent = state.payloads(0.0)
    assert set(sent) == {f"/shrine/node/{n}" for n in range(NUM_NODES)}
    for args in sent.values():
        assert len(args) == 5  # stdev, carrier, gsr0, gsr1, gsr2


def test_presence_channels_independent():
    state = ManualState(smoothing=False)
    state.set(("pres", 2, 0), 0.3)  # node 2 stdev
    state.set(("pres", 2, 1), 0.9)  # node 2 carrier
    state.update()
    args = state.payloads(0.0)["/shrine/node/2"]
    assert args[0] == 0.3
    assert args[1] == 0.9


def test_coupling_is_symmetric_across_both_nodes():
    """Setting a pair once shows up identically on both reporting nodes."""
    state = ManualState(smoothing=False)
    pair_idx = 0
    a, b = GSR_PAIRS[pair_idx]      # e.g. (0, 1)
    state.set(("pair", pair_idx), 0.8)
    state.update()
    sent = state.payloads(0.0)

    slot_a = _slot_of(a, pair_idx)
    slot_b = _slot_of(b, pair_idx)
    assert _gsr(sent[f"/shrine/node/{a}"])[slot_a] == 0.8
    assert _gsr(sent[f"/shrine/node/{b}"])[slot_b] == 0.8


def test_every_pair_reported_identically_by_both_nodes():
    """A distinct value per pair must match on both of that pair's slots."""
    state = ManualState(smoothing=False)
    for p in range(len(GSR_PAIRS)):
        state.set(("pair", p), (p + 1) / 10.0)
    state.update()
    sent = state.payloads(0.0)
    for p, (a, b) in enumerate(GSR_PAIRS):
        val_a = _gsr(sent[f"/shrine/node/{a}"])[_slot_of(a, p)]
        val_b = _gsr(sent[f"/shrine/node/{b}"])[_slot_of(b, p)]
        assert val_a == val_b == (p + 1) / 10.0


def test_instant_vs_smoothing():
    instant = ManualState(smoothing=False)
    instant.set(("pres", 0, 0), 1.0)
    instant.update()
    assert instant.current(("pres", 0, 0)) == 1.0

    eased = ManualState(smoothing=True)
    eased.set(("pres", 0, 0), 1.0)
    eased.update()
    assert 0.0 < eased.current(("pres", 0, 0)) < 1.0


def test_adjust_and_set_clamp():
    state = ManualState(smoothing=False)
    ch = ("pair", 3)
    state.adjust(ch, 5.0)
    assert state.target(ch) == 1.0
    state.adjust(ch, -5.0)
    assert state.target(ch) == 0.0


def test_mute_zeros_output_but_preserves_target():
    state = ManualState(smoothing=False)
    ch = ("pres", 1, 0)
    state.set(ch, 0.7)
    state.update()
    state.toggle_mute(ch)
    assert state.payloads(0.0)["/shrine/node/1"][0] == 0.0
    assert state.target(ch) == 0.7
    state.toggle_mute(ch)
    assert state.payloads(0.0)["/shrine/node/1"][0] == 0.7


def test_muting_a_pair_zeros_both_sides():
    state = ManualState(smoothing=False)
    pair_idx = 5
    a, b = GSR_PAIRS[pair_idx]
    state.set(("pair", pair_idx), 0.6)
    state.update()
    state.toggle_mute(("pair", pair_idx))
    sent = state.payloads(0.0)
    assert _gsr(sent[f"/shrine/node/{a}"])[_slot_of(a, pair_idx)] == 0.0
    assert _gsr(sent[f"/shrine/node/{b}"])[_slot_of(b, pair_idx)] == 0.0


def test_releasing_a_node_zeros_its_couplings_on_both_sides():
    """A released user's presence and every coupling it touches drop to 0."""
    state = ManualState(smoothing=False)
    state.fill_all()
    state.update()
    released = 0
    state.toggle_touch(released)
    sent = state.payloads(0.0)

    # Released node sends nothing.
    assert all(v == 0.0 for v in sent[f"/shrine/node/{released}"])

    # Any pair involving the released node reads 0 from its partner too.
    for p, (a, b) in enumerate(GSR_PAIRS):
        if released in (a, b):
            partner = b if a == released else a
            assert _gsr(sent[f"/shrine/node/{partner}"])[_slot_of(partner, p)] == 0.0


def test_set_node_sets_presence_and_its_pairs():
    state = ManualState(smoothing=False)
    state.set_node(1, 0.5)
    assert state.target(("pres", 1, 0)) == 0.5
    assert state.target(("pres", 1, 1)) == 0.5
    for p, (a, b) in enumerate(GSR_PAIRS):
        if 1 in (a, b):
            assert state.target(("pair", p)) == 0.5


def test_jitter_symmetric_across_pair_and_in_range():
    """Jitter is keyed by pair, so both nodes report a pair identically."""
    state = ManualState(smoothing=False, jitter=True)
    for p in range(len(GSR_PAIRS)):
        state.set(("pair", p), 0.5)
    state.update()
    sent = state.payloads(3.0)
    for args in sent.values():
        assert all(0.0 <= v <= 1.0 for v in args)
    for p, (a, b) in enumerate(GSR_PAIRS):
        val_a = _gsr(sent[f"/shrine/node/{a}"])[_slot_of(a, p)]
        val_b = _gsr(sent[f"/shrine/node/{b}"])[_slot_of(b, p)]
        assert val_a == val_b
