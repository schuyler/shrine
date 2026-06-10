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


def test_noise_symmetric_across_pair_and_in_range():
    """Noise is generated per pair, so both nodes report a pair identically."""
    state = ManualState(smoothing=False, jitter=True, seed=1)
    for p in range(len(GSR_PAIRS)):
        state.set(("pair", p), 0.5)
    for _ in range(20):
        state.update(1.0 / 30.0)
    sent = state.payloads()
    for args in sent.values():
        assert all(0.0 <= v <= 1.0 for v in args)
    for p, (a, b) in enumerate(GSR_PAIRS):
        val_a = _gsr(sent[f"/shrine/node/{a}"])[_slot_of(a, p)]
        val_b = _gsr(sent[f"/shrine/node/{b}"])[_slot_of(b, p)]
        assert val_a == val_b


def test_noise_moves_output_off_the_baseline():
    """With jitter on, the sent value fluctuates around its DC baseline."""
    state = ManualState(smoothing=False, jitter=True, seed=2)
    ch = ("pres", 0, 0)
    state.set(ch, 0.5)
    samples = []
    for _ in range(200):
        state.update(1.0 / 30.0)
        samples.append(state.payloads()["/shrine/node/0"][0])
    assert any(v != 0.5 for v in samples)          # it actually moves
    assert max(samples) - min(samples) > 0.0
    assert abs(sum(samples) / len(samples) - 0.5) < 0.05  # reverts to baseline


def test_noise_floor_at_rest_but_jitter_off_is_clean():
    """A rest channel has a small noise floor; with jitter off it's exactly 0."""
    quiet = ManualState(smoothing=False, jitter=False, seed=3)
    quiet.set(("pres", 0, 0), 0.0)
    for _ in range(50):
        quiet.update(1.0 / 30.0)
    assert quiet.payloads()["/shrine/node/0"][0] == 0.0

    noisy = ManualState(smoothing=False, jitter=True, seed=3)
    noisy.set(("pres", 0, 0), 0.0)
    moved = False
    for _ in range(200):
        noisy.update(1.0 / 30.0)
        if noisy.payloads()["/shrine/node/0"][0] > 0.0:
            moved = True
    assert moved  # rest channel blips above zero from the noise floor


def test_heart_rates_in_human_range():
    import manual
    state = ManualState(seed=11)
    for f in state._hr_freq:
        assert manual.HB_BPM_MIN / 60.0 <= f <= manual.HB_BPM_MAX / 60.0


def test_heartbeat_pulse_is_zero_mean():
    state = ManualState(seed=0)
    # Average the centered pulse over a full cycle of node 0's phase.
    total = 0.0
    samples = 512
    for k in range(samples):
        state._hr_phase[0] = k / samples
        total += state._hb_pulse(0)
    assert abs(total / samples) < 1e-6


def test_coupling_pulses_at_heart_rate(monkeypatch):
    """An active coupling oscillates at heart rate; presence does not pulse.

    OU noise is zeroed here so the heartbeat is isolated and the assertion is
    deterministic; the other tests cover the noise itself.
    """
    import manual
    monkeypatch.setattr(manual, "NOISE_FLOOR", 0.0)
    monkeypatch.setattr(manual, "NOISE_GAIN", 0.0)
    monkeypatch.setattr(manual, "DRIFT_STD", 0.0)

    state = ManualState(smoothing=False, jitter=True, seed=5)
    state.set(("pair", 0), 0.8)      # nodes 0 and 1 in contact
    state.set(("pres", 0, 0), 0.8)   # node 0 presence at the same level

    a, b = GSR_PAIRS[0]
    slot_a = _slot_of(a, 0)
    fps = 60.0
    seconds = 4.0
    pair_series, pres_series = [], []
    for _ in range(int(fps * seconds)):
        state.update(1.0 / fps)
        sent = state.payloads()
        pair_series.append(_gsr(sent[f"/shrine/node/{a}"])[slot_a])
        pres_series.append(sent["/shrine/node/0"][0])

    # Presence carries no heartbeat and (here) no noise -> dead steady.
    assert max(pres_series) - min(pres_series) < 1e-9

    # The coupling visibly pulses, oscillating around its 0.8 baseline.
    assert max(pair_series) - min(pair_series) > 0.05

    mean = sum(pair_series) / len(pair_series)
    beats = sum(
        1 for i in range(1, len(pair_series))
        if (pair_series[i - 1] - mean) <= 0 < (pair_series[i] - mean)
    )
    # Two hearts at 60-100 bpm over 4 s => a handful of upward beats.
    assert 4 <= beats <= 16


def test_seeded_noise_is_reproducible():
    a = ManualState(smoothing=False, jitter=True, seed=7)
    b = ManualState(smoothing=False, jitter=True, seed=7)
    a.set(("pres", 1, 1), 0.4)
    b.set(("pres", 1, 1), 0.4)
    for _ in range(30):
        a.update(1.0 / 30.0)
        b.update(1.0 / 30.0)
    assert a.payloads()["/shrine/node/1"][1] == b.payloads()["/shrine/node/1"][1]
