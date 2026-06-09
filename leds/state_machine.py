"""Leaky-bucket conductor FSM.

Consumes SensorSnapshots and emits CueEvents. All time is injected via dt —
no calls to time.time() or time.monotonic() — making this straightforwardly
unit-testable with accelerated time.
"""

from dataclasses import dataclass
from enum import Enum, auto

from leds.sensor_state import SensorSnapshot


class State(Enum):
    QUIET = auto()
    SEEKING = auto()
    ALIGNING = auto()
    ENERGIZING = auto()
    ASCENDING = auto()


@dataclass(frozen=True)
class StateChangedEvent:
    old: State
    new: State


@dataclass(frozen=True)
class GroupChangedEvent:
    members: frozenset[int]


CueEvent = StateChangedEvent | GroupChangedEvent


class StateMachine:
    """Leaky-bucket conductor FSM.

    Each level has a bucket that fills while its qualifying connection holds
    and drains at half rate when absent. Upward transitions require the bucket
    to be full AND the next level's qualifying condition to have been held
    continuously for confirm_hold seconds. Downward transitions happen when
    the bucket empties. A global idle bucket forces a collapse to Quiet from
    any state after 180 s (configurable) with zero pad engagement.
    """

    def __init__(self, buckets_config: dict, idle_config: dict, confirm_hold: float):
        self._buckets = buckets_config
        self._idle_cfg = idle_config
        self._confirm_hold = confirm_hold

        self._state = State.QUIET
        self._bucket = 0.0
        self._idle = 0.0
        self._confirm_timer = 0.0
        self._last_group: frozenset[int] = frozenset()

    @property
    def state(self) -> State:
        return self._state

    def tick(self, snapshot: SensorSnapshot, dt: float) -> list[CueEvent]:
        """Advance the FSM by dt seconds given the current sensor snapshot.

        Returns a list of CueEvents (may be empty). Events are ordered:
        state-change events precede group-change events within a single tick.
        """
        events: list[CueEvent] = []
        any_engaged = bool(snapshot.engaged)
        group_size = len(snapshot.group_members)

        # Global idle bucket: fills while no pads engaged, drains while any engaged.
        if not any_engaged:
            self._idle += dt
        else:
            self._idle = max(0.0, self._idle - self._idle_cfg["drain_rate"] * dt)

        if self._idle >= self._idle_cfg["timeout"] and self._state != State.QUIET:
            events.append(StateChangedEvent(self._state, State.QUIET))
            self._state = State.QUIET
            self._bucket = 0.0
            self._idle = 0.0
            self._confirm_timer = 0.0
            events.extend(self._check_group(snapshot))
            return events

        if self._state == State.QUIET:
            if any_engaged:
                events.extend(self._transition_to(State.SEEKING))

        elif self._state == State.SEEKING:
            cfg = self._buckets["seeking"]
            if any_engaged:
                self._bucket = min(cfg["full_at"], self._bucket + cfg["fill_rate"] * dt)
            else:
                self._bucket = max(0.0, self._bucket - cfg["drain_rate"] * dt)

            if group_size >= 2:
                self._confirm_timer += dt
            else:
                self._confirm_timer = 0.0

            if self._bucket >= cfg["full_at"] and self._confirm_timer >= self._confirm_hold:
                events.extend(self._transition_to(State.ALIGNING))

        elif self._state == State.ALIGNING:
            cfg = self._buckets["aligning"]
            if group_size >= 2:
                self._bucket = min(cfg["full_at"], self._bucket + cfg["fill_rate"] * dt)
            else:
                self._bucket = max(0.0, self._bucket - cfg["drain_rate"] * dt)

            if group_size >= 3:
                self._confirm_timer += dt
            else:
                self._confirm_timer = 0.0

            if self._bucket >= cfg["full_at"] and self._confirm_timer >= self._confirm_hold:
                events.extend(self._transition_to(State.ENERGIZING))
            elif self._bucket <= 0.0:
                events.extend(self._transition_to(State.SEEKING))

        elif self._state == State.ENERGIZING:
            cfg = self._buckets["energizing"]
            if group_size >= 3:
                self._bucket = min(cfg["full_at"], self._bucket + cfg["fill_rate"] * dt)
            else:
                self._bucket = max(0.0, self._bucket - cfg["drain_rate"] * dt)

            if group_size >= 4:
                self._confirm_timer += dt
            else:
                self._confirm_timer = 0.0

            if self._bucket >= cfg["full_at"] and self._confirm_timer >= self._confirm_hold:
                events.extend(self._transition_to(State.ASCENDING))
            elif self._bucket <= 0.0:
                events.extend(self._transition_to(State.ALIGNING))

        elif self._state == State.ASCENDING:
            # Fixed dwell, drains unconditionally.
            self._bucket = max(0.0, self._bucket - dt)
            if self._bucket <= 0.0:
                events.extend(self._transition_to(State.ENERGIZING))

        events.extend(self._check_group(snapshot))
        return events

    # ------------------------------------------------------------------

    def _transition_to(self, new_state: State) -> list[CueEvent]:
        old = self._state
        self._state = new_state
        self._confirm_timer = 0.0
        self._bucket = self._entry_seed(new_state)
        return [StateChangedEvent(old, new_state)]

    def _entry_seed(self, state: State) -> float:
        if state == State.SEEKING:
            return self._buckets["seeking"]["entry_seed"]
        if state == State.ALIGNING:
            return self._buckets["aligning"]["entry_seed"]
        if state == State.ENERGIZING:
            return self._buckets["energizing"]["entry_seed"]
        if state == State.ASCENDING:
            return self._buckets["ascending"]["dwell"]
        return 0.0

    def _check_group(self, snapshot: SensorSnapshot) -> list[CueEvent]:
        if snapshot.group_members != self._last_group:
            self._last_group = snapshot.group_members
            return [GroupChangedEvent(snapshot.group_members)]
        return []
