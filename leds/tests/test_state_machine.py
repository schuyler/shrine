"""Tests for leds.state_machine."""

import pytest

from leds.sensor_state import SensorSnapshot
from leds.state_machine import (
    CueEvent,
    GroupChangedEvent,
    State,
    StateChangedEvent,
    StateMachine,
)

# Minimal conductor config (reduced timings for fast tests)
_BUCKETS = {
    "seeking": {"fill_rate": 1.0, "drain_rate": 0.5, "full_at": 10.0, "entry_seed": 0.0},
    "aligning": {"fill_rate": 1.0, "drain_rate": 0.5, "full_at": 10.0, "entry_seed": 5.0},
    "energizing": {"fill_rate": 1.0, "drain_rate": 0.5, "full_at": 5.0, "entry_seed": 2.0},
    "ascending": {"dwell": 6.0},
}
_IDLE = {"timeout": 20.0, "drain_rate": 1.0}
_CONFIRM_HOLD = 1.0


def _make_fsm() -> StateMachine:
    return StateMachine(_BUCKETS, _IDLE, _CONFIRM_HOLD)


def _snap(
    engaged: set[int] | None = None,
    edges: set[tuple[int, int]] | None = None,
    group_members: set[int] | None = None,
) -> SensorSnapshot:
    e = frozenset(engaged or set())
    ed = frozenset(edges or set())
    g = frozenset(group_members or set())
    return SensorSnapshot(
        engaged=e,
        edges=ed,
        group_members=g,
        raw_cap=(0.0, 0.0, 0.0, 0.0),
        raw_gsr=(0.0,) * 6,
    )


def _state_events(events: list) -> list[StateChangedEvent]:
    return [e for e in events if isinstance(e, StateChangedEvent)]


def _group_events(events: list) -> list[GroupChangedEvent]:
    return [e for e in events if isinstance(e, GroupChangedEvent)]


def _tick_for(fsm: StateMachine, snap: SensorSnapshot, total: float, dt: float = 0.1) -> list:
    events = []
    elapsed = 0.0
    while elapsed < total:
        step = min(dt, total - elapsed)
        events.extend(fsm.tick(snap, step))
        elapsed += step
    return events


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_starts_quiet(self):
        assert _make_fsm().state == State.QUIET

    def test_no_events_when_quiet_and_empty(self):
        fsm = _make_fsm()
        events = fsm.tick(_snap(), 1.0)
        assert events == []


# ---------------------------------------------------------------------------
# Quiet → Seeking
# ---------------------------------------------------------------------------

class TestQuietToSeeking:
    def test_transitions_immediately_on_engagement(self):
        fsm = _make_fsm()
        events = fsm.tick(_snap(engaged={0}), 0.1)
        se = _state_events(events)
        assert len(se) == 1
        assert se[0].old == State.QUIET
        assert se[0].new == State.SEEKING

    def test_no_transition_without_engagement(self):
        fsm = _make_fsm()
        fsm.tick(_snap(), 5.0)
        assert fsm.state == State.QUIET

    def test_group_event_emitted_on_engagement(self):
        fsm = _make_fsm()
        events = fsm.tick(_snap(engaged={0}, group_members={0}), 0.1)
        ge = _group_events(events)
        assert len(ge) == 1
        assert ge[0].members == frozenset({0})


# ---------------------------------------------------------------------------
# Seeking → Aligning
# ---------------------------------------------------------------------------

class TestSeekingToAligning:
    def test_transitions_when_bucket_full_and_pair_held(self):
        fsm = _make_fsm()
        # Get to Seeking
        fsm.tick(_snap(engaged={0}), 0.1)
        # Fill bucket (full_at=10) while also holding group≥2 for confirm_hold=1
        pair_snap = _snap(engaged={0, 1}, group_members={0, 1})
        events = _tick_for(fsm, pair_snap, 10.5)
        se = _state_events(events)
        assert any(e.new == State.ALIGNING for e in se)

    def test_no_transition_if_bucket_not_full(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        pair_snap = _snap(engaged={0, 1}, group_members={0, 1})
        _tick_for(fsm, pair_snap, 5.0)
        assert fsm.state == State.SEEKING

    def test_no_transition_if_pair_not_held(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        # Fill bucket but never get a pair
        _tick_for(fsm, _snap(engaged={0}), 10.0)
        assert fsm.state == State.SEEKING

    def test_confirm_timer_resets_on_pair_loss(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        pair_snap = _snap(engaged={0, 1}, group_members={0, 1})
        solo_snap = _snap(engaged={0})
        # Accumulate bucket, get close on confirm timer, then lose pair
        _tick_for(fsm, pair_snap, 9.5)
        _tick_for(fsm, solo_snap, 0.5)
        # confirm timer reset; need another 1s of pair to advance
        events = _tick_for(fsm, pair_snap, 0.5)
        assert not any(e.new == State.ALIGNING for e in _state_events(events))


# ---------------------------------------------------------------------------
# Aligning → Seeking (decay)
# ---------------------------------------------------------------------------

class TestAligningDecay:
    def _get_to_aligning(self) -> StateMachine:
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        pair_snap = _snap(engaged={0, 1}, group_members={0, 1})
        _tick_for(fsm, pair_snap, 11.0)
        assert fsm.state == State.ALIGNING
        return fsm

    def test_decays_to_seeking_when_bucket_empties(self):
        fsm = self._get_to_aligning()
        # Bucket was seeded at entry_seed=5 and may have partially filled during
        # setup; run long enough to drain past any reasonable starting level.
        events = _tick_for(fsm, _snap(), 25.0)
        se = _state_events(events)
        assert any(e.new == State.SEEKING for e in se)

    def test_survives_brief_pair_loss(self):
        fsm = self._get_to_aligning()
        # bucket seeded at 5, drains at 0.5/s; 5s of no pair → bucket at 2.5
        _tick_for(fsm, _snap(), 5.0)
        assert fsm.state == State.ALIGNING

    def test_earned_robustness(self):
        fsm = self._get_to_aligning()
        # Fill bucket to full (full_at=10) then lose pair
        pair_snap = _snap(engaged={0, 1}, group_members={0, 1})
        _tick_for(fsm, pair_snap, 5.0)
        # Now bucket near full; drain at 0.5/s → ~20s to empty
        events = _tick_for(fsm, _snap(), 5.0)
        assert not any(e.new == State.SEEKING for e in _state_events(events))


# ---------------------------------------------------------------------------
# Aligning → Energizing
# ---------------------------------------------------------------------------

class TestAligningToEnergizing:
    def _get_to_aligning(self) -> StateMachine:
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        _tick_for(fsm, _snap(engaged={0, 1}, group_members={0, 1}), 11.0)
        assert fsm.state == State.ALIGNING
        return fsm

    def test_transitions_with_full_bucket_and_trio_held(self):
        fsm = self._get_to_aligning()
        trio_snap = _snap(engaged={0, 1, 2}, group_members={0, 1, 2})
        events = _tick_for(fsm, trio_snap, 11.0)
        assert any(e.new == State.ENERGIZING for e in _state_events(events))


# ---------------------------------------------------------------------------
# Energizing → Ascending
# ---------------------------------------------------------------------------

class TestEnergizingToAscending:
    def _get_to_energizing(self) -> StateMachine:
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        _tick_for(fsm, _snap(engaged={0, 1}, group_members={0, 1}), 11.0)
        _tick_for(fsm, _snap(engaged={0, 1, 2}, group_members={0, 1, 2}), 11.0)
        assert fsm.state == State.ENERGIZING
        return fsm

    def test_transitions_to_ascending(self):
        fsm = self._get_to_energizing()
        full_snap = _snap(engaged={0, 1, 2, 3}, group_members={0, 1, 2, 3})
        events = _tick_for(fsm, full_snap, 7.0)
        assert any(e.new == State.ASCENDING for e in _state_events(events))


# ---------------------------------------------------------------------------
# Ascending dwell and pulse
# ---------------------------------------------------------------------------

class TestAscending:
    def _get_to_ascending(self) -> StateMachine:
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        _tick_for(fsm, _snap(engaged={0, 1}, group_members={0, 1}), 11.0)
        _tick_for(fsm, _snap(engaged={0, 1, 2}, group_members={0, 1, 2}), 11.0)
        full = _snap(engaged={0, 1, 2, 3}, group_members={0, 1, 2, 3})
        _tick_for(fsm, full, 7.0)
        assert fsm.state == State.ASCENDING
        return fsm

    def test_decays_to_energizing_after_dwell(self):
        fsm = self._get_to_ascending()
        # dwell=6s; energizing entry_seed=2, so it re-seeds at 2
        events = _tick_for(fsm, _snap(), 7.0)
        se = _state_events(events)
        assert any(e.new == State.ENERGIZING for e in se)

    def test_ascending_pulse_re_climbs(self):
        fsm = self._get_to_ascending()
        full = _snap(engaged={0, 1, 2, 3}, group_members={0, 1, 2, 3})
        # Run long enough for the dwell to expire, drop to Energizing, then re-climb.
        events = _tick_for(fsm, full, 15.0)
        se = _state_events(events)
        assert any(e.new == State.ENERGIZING for e in se), "expected decay to Energizing"
        assert any(e.new == State.ASCENDING for e in se), "expected re-climb to Ascending"


# ---------------------------------------------------------------------------
# Global idle collapse
# ---------------------------------------------------------------------------

class TestIdleCollapse:
    def test_collapses_to_quiet_from_seeking(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        assert fsm.state == State.SEEKING
        events = _tick_for(fsm, _snap(), 21.0)
        se = _state_events(events)
        assert any(e.new == State.QUIET for e in se)

    def test_collapses_to_quiet_from_aligning(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        _tick_for(fsm, _snap(engaged={0, 1}, group_members={0, 1}), 11.0)
        assert fsm.state == State.ALIGNING
        events = _tick_for(fsm, _snap(), 21.0)
        assert any(e.new == State.QUIET for e in _state_events(events))

    def test_idle_bucket_drains_while_engaged(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}), 0.1)
        # Fill idle a bit, then engage to drain it
        _tick_for(fsm, _snap(), 5.0)
        _tick_for(fsm, _snap(engaged={0}), 5.0)
        # 5s idle filled, 5s drained at 1/s → idle=0; no collapse
        assert fsm.state != State.QUIET

    def test_no_idle_collapse_in_quiet(self):
        fsm = _make_fsm()
        events = _tick_for(fsm, _snap(), 50.0)
        se = _state_events(events)
        assert not any(e.new == State.QUIET for e in se)


# ---------------------------------------------------------------------------
# Group topology events
# ---------------------------------------------------------------------------

class TestGroupEvents:
    def test_group_event_emitted_on_change(self):
        fsm = _make_fsm()
        events = fsm.tick(_snap(engaged={0}, group_members={0}), 0.1)
        ge = _group_events(events)
        assert len(ge) == 1
        assert ge[0].members == frozenset({0})

    def test_no_group_event_when_unchanged(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}, group_members={0}), 0.1)
        events = fsm.tick(_snap(engaged={0}, group_members={0}), 0.1)
        assert _group_events(events) == []

    def test_group_event_on_member_added(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0}, group_members={0}), 0.1)
        events = fsm.tick(_snap(engaged={0, 1}, group_members={0, 1}), 0.1)
        ge = _group_events(events)
        assert len(ge) == 1
        assert ge[0].members == frozenset({0, 1})

    def test_group_event_on_member_removed(self):
        fsm = _make_fsm()
        fsm.tick(_snap(engaged={0, 1}, group_members={0, 1}), 0.1)
        events = fsm.tick(_snap(engaged={0}, group_members={0}), 0.1)
        ge = _group_events(events)
        assert len(ge) == 1
        assert ge[0].members == frozenset({0})


# ---------------------------------------------------------------------------
# Integration: full arc progression
# ---------------------------------------------------------------------------

class TestFullArc:
    def test_full_progression_quiet_to_ascending(self):
        fsm = _make_fsm()
        states_seen = []

        def run(snap, duration):
            events = _tick_for(fsm, snap, duration)
            for e in _state_events(events):
                states_seen.append(e.new)

        run(_snap(engaged={0}), 0.1)
        run(_snap(engaged={0, 1}, group_members={0, 1}), 11.0)
        run(_snap(engaged={0, 1, 2}, group_members={0, 1, 2}), 11.0)
        run(_snap(engaged={0, 1, 2, 3}, group_members={0, 1, 2, 3}), 7.0)

        assert State.SEEKING in states_seen
        assert State.ALIGNING in states_seen
        assert State.ENERGIZING in states_seen
        assert State.ASCENDING in states_seen
