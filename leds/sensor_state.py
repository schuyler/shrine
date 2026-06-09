"""Canonical sensor state for the Shrine conductor.

Receives raw firmware values, applies Schmitt-trigger + hold-time debouncing,
and exposes a thread-safe snapshot of debounced pad presence and pair
connections with connected-component membership.
"""

import threading
from dataclasses import dataclass

# 6 unique pad-pair combinations, 0-indexed.
GSR_PAIRS: list[tuple[int, int]] = [
    (0, 1), (0, 2), (0, 3),
    (1, 2), (1, 3),
    (2, 3),
]

# Node N GSR slots → GSR_PAIRS index.
# Node 0 (pad 0) sees pads 1,2,3 → pairs (0,1),(0,2),(0,3) → indices 0,1,2
# Node 1 (pad 1) sees pads 2,3,0 → pairs (1,2),(1,3),(0,1) → indices 3,4,0
# Node 2 (pad 2) sees pads 3,0,1 → pairs (2,3),(0,2),(1,2) → indices 5,1,3
# Node 3 (pad 3) sees pads 0,1,2 → pairs (0,3),(1,3),(2,3) → indices 2,4,5
NODE_GSR_MAPPING: list[list[int]] = [
    [0, 1, 2],
    [3, 4, 0],
    [5, 1, 3],
    [2, 4, 5],
]

_N_PADS = 4
_N_PAIRS = len(GSR_PAIRS)


@dataclass(frozen=True)
class SensorSnapshot:
    engaged: frozenset[int]                  # 0-indexed pad IDs that have confirmed cap presence
    edges: frozenset[tuple[int, int]]        # confirmed pair connections, canonical order (a < b)
    group_members: frozenset[int]            # pads in the largest connected component
    raw_cap: tuple[float, ...]               # 4 raw cap values, indexed by pad (0-3)
    raw_gsr: tuple[float, ...]               # 6 raw GSR values, indexed by GSR_PAIRS order


def _largest_component(
    engaged: frozenset[int],
    edges: frozenset[tuple[int, int]],
) -> frozenset[int]:
    if not engaged:
        return frozenset()

    parent = {p: p for p in engaged}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for a, b in edges:
        if a in engaged and b in engaged:
            union(a, b)

    components: dict[int, set[int]] = {}
    for p in engaged:
        root = find(p)
        components.setdefault(root, set()).add(p)

    return frozenset(max(components.values(), key=len))


class SensorState:
    """Thread-safe sensor state with Schmitt-trigger debouncing.

    Call update_node() from the OSC thread whenever a /shrine/node/* message
    arrives, then call tick(dt) from the conductor loop to advance hold timers.
    snapshot() is safe to call from any thread at any time.
    """

    def __init__(self, config: dict):
        self._cfg = config
        self._lock = threading.Lock()

        self._raw_cap = [0.0] * _N_PADS
        self._raw_gsr = [0.0] * _N_PAIRS

        self._cap_engaged = [False] * _N_PADS
        self._cap_pending = [0.0] * _N_PADS

        self._gsr_connected = [False] * _N_PAIRS
        self._gsr_pending = [0.0] * _N_PAIRS

    def update_node(
        self,
        node_id: int,
        stdev: float,
        carrier_mag: float,  # accepted to match OSC format; not stored
        gsr0: float,
        gsr1: float,
        gsr2: float,
    ) -> None:
        with self._lock:
            self._raw_cap[node_id] = stdev
            for slot, val in enumerate((gsr0, gsr1, gsr2)):
                self._raw_gsr[NODE_GSR_MAPPING[node_id][slot]] = val

    def tick(self, dt: float) -> None:
        cfg = self._cfg
        with self._lock:
            for i in range(_N_PADS):
                self._cap_engaged[i], self._cap_pending[i] = _schmitt(
                    value=self._raw_cap[i],
                    state=self._cap_engaged[i],
                    pending=self._cap_pending[i],
                    dt=dt,
                    on_thresh=cfg["cap_on_threshold"],
                    off_thresh=cfg["cap_off_threshold"],
                    hold_on=cfg["cap_hold_on"],
                    hold_off=cfg["cap_hold_off"],
                )

            for i in range(_N_PAIRS):
                a, b = GSR_PAIRS[i]
                both_engaged = self._cap_engaged[a] and self._cap_engaged[b]
                if not both_engaged:
                    # An edge with an absent endpoint is immediately invalid.
                    self._gsr_connected[i] = False
                    self._gsr_pending[i] = 0.0
                else:
                    self._gsr_connected[i], self._gsr_pending[i] = _schmitt(
                        value=self._raw_gsr[i],
                        state=self._gsr_connected[i],
                        pending=self._gsr_pending[i],
                        dt=dt,
                        on_thresh=cfg["gsr_on_threshold"],
                        off_thresh=cfg["gsr_off_threshold"],
                        hold_on=cfg["gsr_hold_on"],
                        hold_off=cfg["gsr_hold_off"],
                    )

    def snapshot(self) -> SensorSnapshot:
        with self._lock:
            engaged = frozenset(i for i in range(_N_PADS) if self._cap_engaged[i])
            edges = frozenset(
                GSR_PAIRS[i] for i in range(_N_PAIRS) if self._gsr_connected[i]
            )
            group_members = _largest_component(engaged, edges)
            return SensorSnapshot(
                engaged=engaged,
                edges=edges,
                group_members=group_members,
                raw_cap=tuple(self._raw_cap),
                raw_gsr=tuple(self._raw_gsr),
            )


def _schmitt(
    value: float,
    state: bool,
    pending: float,
    dt: float,
    on_thresh: float,
    off_thresh: float,
    hold_on: float,
    hold_off: float,
) -> tuple[bool, float]:
    """Advance one Schmitt-trigger step. Returns (new_state, new_pending)."""
    if not state:
        if value >= on_thresh:
            pending += dt
            if pending >= hold_on:
                return True, 0.0
        else:
            pending = 0.0
    else:
        if value <= off_thresh:
            pending += dt
            if pending >= hold_off:
                return False, 0.0
        else:
            pending = 0.0
    return state, pending
