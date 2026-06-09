"""Tests for the manual sensor simulator's UI-independent state model."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from manual import NUM_CHANNELS, NUM_NODES, ManualState


def test_payload_shape_matches_firmware():
    """Each node emits one address with exactly five floats."""
    state = ManualState(smoothing=False)
    state.update()
    sent = state.payloads(0.0)
    assert set(sent) == {f"/shrine/node/{n}" for n in range(NUM_NODES)}
    for args in sent.values():
        assert len(args) == NUM_CHANNELS == 5


def test_channels_are_independent():
    """stdev and carrier on the same node move separately."""
    state = ManualState(smoothing=False)
    state.set(2, 0, 0.3)  # node 2 stdev
    state.set(2, 1, 0.9)  # node 2 carrier
    state.update()
    args = state.payloads(0.0)["/shrine/node/2"]
    assert args[0] == 0.3
    assert args[1] == 0.9


def test_instant_vs_smoothing():
    """Without smoothing the value snaps; with smoothing it eases."""
    instant = ManualState(smoothing=False)
    instant.set(0, 0, 1.0)
    instant.update()
    assert instant.current[0][0] == 1.0

    eased = ManualState(smoothing=True)
    eased.set(0, 0, 1.0)
    eased.update()
    assert 0.0 < eased.current[0][0] < 1.0


def test_adjust_and_set_clamp():
    state = ManualState(smoothing=False)
    state.adjust(0, 0, 5.0)
    assert state.target[0][0] == 1.0
    state.adjust(0, 0, -5.0)
    assert state.target[0][0] == 0.0


def test_bulk_helpers():
    state = ManualState(smoothing=False)
    state.fill_all()
    assert all(v == 1.0 for row in state.target for v in row)
    state.zero_all()
    assert all(v == 0.0 for row in state.target for v in row)
    state.set_node(1, 0.5)
    assert all(v == 0.5 for v in state.target[1])
    assert all(v == 0.0 for v in state.target[0])


def test_mute_zeros_output_but_preserves_target():
    state = ManualState(smoothing=False)
    state.set(1, 2, 0.7)
    state.update()
    state.toggle_mute(1, 2)
    args = state.payloads(0.0)["/shrine/node/1"]
    assert args[2] == 0.0          # output suppressed
    assert state.target[1][2] == 0.7  # held level preserved
    # Unmuting restores the held level.
    state.toggle_mute(1, 2)
    args = state.payloads(0.0)["/shrine/node/1"]
    assert args[2] == 0.7


def test_touch_release_whole_node():
    state = ManualState(smoothing=False)
    state.set_node(0, 0.5)
    state.update()
    assert not state.node_released(0)

    state.toggle_touch(0)          # release
    assert state.node_released(0)
    assert all(v == 0.0 for v in state.payloads(0.0)["/shrine/node/0"])
    assert all(v == 0.5 for v in state.target[0])  # pose preserved

    state.toggle_touch(0)          # touch again
    assert not state.node_released(0)
    assert all(v == 0.5 for v in state.payloads(0.0)["/shrine/node/0"])


def test_touch_releases_when_partially_muted():
    """A node with any live channel releases fully on touch toggle."""
    state = ManualState(smoothing=False)
    state.set_node(3, 0.4)
    state.toggle_mute(3, 0)        # one channel already muted
    state.toggle_touch(3)
    assert state.node_released(3)


def test_jitter_stays_in_range_and_preserves_target():
    state = ManualState(smoothing=False, jitter=True)
    state.set_node(0, 0.5)
    state.update()
    args = state.payloads(3.0)["/shrine/node/0"]
    assert all(0.0 <= v <= 1.0 for v in args)
    # Jitter must not disturb the held target.
    assert all(v == 0.5 for v in state.target[0])
