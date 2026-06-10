#!/usr/bin/env python3
"""Manually controllable OSC sensor simulator for the Shrine sound engine.

Unlike ``generator.py``, which plays an automated scenario, this tool puts
every channel under direct keyboard control. It mirrors the firmware's actual
OSC output exactly: for each of the four nodes it streams ``/shrine/node/N``
with five floats — ``self_stdev``, ``self_carrier_mag`` and three ``gsr_mag``
cross-couplings (see edge-node/README.md, "OSC Output").

The control model matches the physical reality the receiver reconstructs:

* Each node has its own **presence** (``stdev``, ``carrier``) — independent.
* Each unordered **pair** of nodes shares one **coupling** (GSR) value. The
  firmware reports that pair from *both* nodes' slots, so the simulator drives
  it from a single source and writes it to both slots — keeping the two sides
  symmetric (set one, both move). A released user's couplings drop to zero on
  both sides.

Usage:
    python osc-sim/manual.py [--host HOST] [--port PORT] [--rate HZ]
    python osc-sim/manual.py --targets 255.255.255.255:57120 ...

Controls (shown in the footer at all times):
    arrows / hjkl   move the cursor between channels
    + / =           raise selected channel by the step
    - / _           lower selected channel by the step
    ] / [           fine adjust by 0.01
    0-9             set selected channel to 0.0 .. 0.9
    space           set selected channel to 1.0
    x               mute / unmute the selected channel (keeps its level)
    t               touch / release the selected node (its presence + couplings)
    n / m           zero / max the selected node (presence + its couplings)
    z / f           zero / fill every channel
    s               toggle smoothing (eased vs. instant)
    J               toggle organic jitter
    q               quit
"""

import argparse
import curses
import sys
import time

from pythonosc.udp_client import SimpleUDPClient

# Reuse the broadcast client and noise generator from the automated simulator,
# and the canonical pair layout from the receiver, so everything shares one
# source of truth for those behaviours.
from generator import BroadcastUDPClient, layered_noise
from leds.sensor_state import GSR_PAIRS as NODE_PAIRS, NODE_GSR_MAPPING

NUM_NODES = 4

# Per-node presence floats, in the order the firmware sends them.
PRESENCE_LABELS = ("stdev", "carrier")
NUM_PRESENCE = len(PRESENCE_LABELS)

NUM_PAIRS = len(NODE_PAIRS)  # 6 unordered node pairs

STEP = 0.05          # coarse adjust per keypress
FINE_STEP = 0.01     # fine adjust per keypress
SMOOTHING_RATE = 0.2  # per-tick easing toward target when smoothing is on
BAR_WIDTH = 8        # filled-bar width in characters

# Per-channel jitter phase offsets. Pairs are keyed by pair index (not by node)
# so both nodes reporting a pair get identical jitter and stay symmetric.
_PRESENCE_OFFSET = 1.1
_PAIR_OFFSET_BASE = 100.0


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class ManualState:
    """The channels the user drives, independent of any UI.

    Presence channels (4 nodes × {stdev, carrier}) and pair couplings (6) each
    track a ``target`` (what the user dialled in) and a ``current`` value that is
    sent over OSC. With smoothing enabled, ``current`` eases toward ``target``
    each tick; otherwise it snaps. Mute is a non-destructive layer: a muted
    channel sends 0.0 but keeps its target. Releasing a node ("touch/release")
    suppresses its presence and every coupling it participates in.
    """

    def __init__(self, smoothing: bool = True, jitter: bool = False):
        self.pres_target = [[0.0] * NUM_PRESENCE for _ in range(NUM_NODES)]
        self.pres_current = [[0.0] * NUM_PRESENCE for _ in range(NUM_NODES)]
        self.pres_muted = [[False] * NUM_PRESENCE for _ in range(NUM_NODES)]
        self.pair_target = [0.0] * NUM_PAIRS
        self.pair_current = [0.0] * NUM_PAIRS
        self.pair_muted = [False] * NUM_PAIRS
        self.released = [False] * NUM_NODES
        self.smoothing = smoothing
        self.jitter = jitter

    # ---- channel addressing -------------------------------------------------
    # A channel key is ("pres", node, idx) or ("pair", pair_idx). The ordered
    # list below is what the views navigate and render.

    @staticmethod
    def channels() -> list:
        chans = []
        for n in range(NUM_NODES):
            for i in range(NUM_PRESENCE):
                chans.append(("pres", n, i))
        for p in range(NUM_PAIRS):
            chans.append(("pair", p))
        return chans

    def label(self, ch) -> str:
        if ch[0] == "pres":
            return f"n{ch[1]} {PRESENCE_LABELS[ch[2]]}"
        a, b = NODE_PAIRS[ch[1]]
        return f"{a}-{b}"

    def target(self, ch) -> float:
        return self.pres_target[ch[1]][ch[2]] if ch[0] == "pres" else self.pair_target[ch[1]]

    def current(self, ch) -> float:
        return self.pres_current[ch[1]][ch[2]] if ch[0] == "pres" else self.pair_current[ch[1]]

    def muted(self, ch) -> bool:
        return self.pres_muted[ch[1]][ch[2]] if ch[0] == "pres" else self.pair_muted[ch[1]]

    def set(self, ch, value: float) -> None:
        value = _clamp(value)
        if ch[0] == "pres":
            self.pres_target[ch[1]][ch[2]] = value
        else:
            self.pair_target[ch[1]] = value

    def adjust(self, ch, delta: float) -> None:
        self.set(ch, self.target(ch) + delta)

    def toggle_mute(self, ch) -> None:
        if ch[0] == "pres":
            self.pres_muted[ch[1]][ch[2]] = not self.pres_muted[ch[1]][ch[2]]
        else:
            self.pair_muted[ch[1]] = not self.pair_muted[ch[1]]

    # ---- node-level helpers -------------------------------------------------

    def toggle_touch(self, node: int) -> None:
        """Touch or release a whole user (its presence and all its couplings)."""
        self.released[node] = not self.released[node]

    def node_released(self, node: int) -> bool:
        return self.released[node]

    def set_node(self, node: int, value: float) -> None:
        """Set a node's presence and every coupling it participates in."""
        value = _clamp(value)
        for i in range(NUM_PRESENCE):
            self.pres_target[node][i] = value
        for p, (a, b) in enumerate(NODE_PAIRS):
            if node in (a, b):
                self.pair_target[p] = value

    def zero_all(self) -> None:
        for n in range(NUM_NODES):
            for i in range(NUM_PRESENCE):
                self.pres_target[n][i] = 0.0
        for p in range(NUM_PAIRS):
            self.pair_target[p] = 0.0

    def fill_all(self) -> None:
        for n in range(NUM_NODES):
            for i in range(NUM_PRESENCE):
                self.pres_target[n][i] = 1.0
        for p in range(NUM_PAIRS):
            self.pair_target[p] = 1.0

    # ---- per-tick advance + OSC ---------------------------------------------

    def _ease(self, current: float, target: float) -> float:
        if not self.smoothing:
            return target
        return current + SMOOTHING_RATE * (target - current)

    def update(self) -> None:
        for n in range(NUM_NODES):
            for i in range(NUM_PRESENCE):
                self.pres_current[n][i] = self._ease(self.pres_current[n][i], self.pres_target[n][i])
        for p in range(NUM_PAIRS):
            self.pair_current[p] = self._ease(self.pair_current[p], self.pair_target[p])

    def payloads(self, t: float) -> dict:
        """Build the OSC payload for each node from the current values.

        Each node's three GSR slots are filled from the shared pair values via
        NODE_GSR_MAPPING, so both nodes of a pair always report the same number.
        """
        sent = {}
        for n in range(NUM_NODES):
            args = []
            for i in range(NUM_PRESENCE):
                if self.released[n] or self.pres_muted[n][i]:
                    args.append(0.0)
                    continue
                v = self.pres_current[n][i]
                if self.jitter:
                    v += layered_noise(t, (n * NUM_PRESENCE + i) * _PRESENCE_OFFSET)
                args.append(_clamp(v))

            for slot in range(3):
                p = NODE_GSR_MAPPING[n][slot]
                a, b = NODE_PAIRS[p]
                if self.pair_muted[p] or self.released[a] or self.released[b]:
                    args.append(0.0)
                    continue
                v = self.pair_current[p]
                if self.jitter:
                    # Keyed by pair, not node, so both sides jitter identically.
                    v += layered_noise(t, (_PAIR_OFFSET_BASE + p) * _PRESENCE_OFFSET)
                args.append(_clamp(v))

            sent[f"/shrine/node/{n}"] = args
        return sent

    def send(self, clients: list, t: float) -> dict:
        sent = self.payloads(t)
        for address, args in sent.items():
            for client in clients:
                client.send_message(address, args)
        return sent


# ---------------------------------------------------------------------------
# Curses TUI
# ---------------------------------------------------------------------------

LABEL_W = 9    # left-hand row-label column
CELL_W = 16    # per-node / per-pair value column: "[████░░░░] 0.55 "
PAIR_LABEL_W = 5
PAIR_COLS = 3  # couplings laid out in a 2×3 grid


def _fmt_cell(current: float, target: float, muted: bool) -> str:
    filled = round(_clamp(current) * BAR_WIDTH)
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    return f"[{bar}] {'mute' if muted else f'{target:.2f}'}"


def _cell_attr(is_sel: bool, dimmed: bool):
    if is_sel:
        return curses.A_REVERSE
    if dimmed:
        return curses.A_DIM
    return curses.A_NORMAL


def _draw(stdscr, state: ManualState, sel: int, header: str):
    stdscr.erase()
    max_rows, max_cols = stdscr.getmaxyx()
    channels = state.channels()
    sel_ch = channels[sel]

    def put(row, col, text, attr=curses.A_NORMAL):
        if row >= max_rows or col >= max_cols:
            return
        try:
            stdscr.addstr(row, col, text[: max_cols - col - 1], attr)
        except curses.error:
            pass

    put(0, 0, header, curses.A_BOLD)
    put(1, 0, f"smoothing:{'on' if state.smoothing else 'off'}  "
             f"jitter:{'on' if state.jitter else 'off'}", curses.A_DIM)

    # --- Presence block ---
    base = 3
    for n in range(NUM_NODES):
        col = LABEL_W + n * CELL_W
        label = f"node{n} REL" if state.released[n] else f"node{n}"
        put(base, col, label.center(CELL_W - 1), curses.A_BOLD)
    for i in range(NUM_PRESENCE):
        row = base + 1 + i
        put(row, 0, PRESENCE_LABELS[i].rjust(LABEL_W - 1))
        for n in range(NUM_NODES):
            col = LABEL_W + n * CELL_W
            ch = ("pres", n, i)
            muted = state.pres_muted[n][i]
            dimmed = muted or state.released[n]
            cell = _fmt_cell(state.pres_current[n][i], state.pres_target[n][i], muted)
            put(row, col, cell, _cell_attr(ch == sel_ch, dimmed))

    # --- Couplings block ---
    cbase = base + 1 + NUM_PRESENCE + 1
    put(cbase, 0, "COUPLINGS (gsr pairs)", curses.A_BOLD)
    for p in range(NUM_PAIRS):
        r, c = divmod(p, PAIR_COLS)
        row = cbase + 1 + r
        col = c * (PAIR_LABEL_W + CELL_W)
        a, b = NODE_PAIRS[p]
        put(row, col, f"{a}-{b}".rjust(PAIR_LABEL_W - 1))
        ch = ("pair", p)
        muted = state.pair_muted[p]
        dimmed = muted or state.released[a] or state.released[b]
        cell = _fmt_cell(state.pair_current[p], state.pair_target[p], muted)
        put(row, col + PAIR_LABEL_W, cell, _cell_attr(ch == sel_ch, dimmed))

    # --- Status + help ---
    status_row = cbase + 1 + (NUM_PAIRS + PAIR_COLS - 1) // PAIR_COLS + 1
    sel_state = "muted" if state.muted(sel_ch) else f"{state.target(sel_ch):.2f}"
    put(status_row, 0,
        f"selected: {state.label(sel_ch)} = {sel_state}   step {STEP:.2f}",
        curses.A_BOLD)
    put(status_row + 2, 0,
        "arrows/hjkl move  +/- adjust  ]/[ fine  0-9 set  space=1.0",
        curses.A_DIM)
    put(status_row + 3, 0,
        "x mute  t touch/release node  n/m zero/max node  z/f zero/fill all",
        curses.A_DIM)
    put(status_row + 4, 0, "s smooth  J jitter  q quit", curses.A_DIM)

    stdscr.refresh()


def _loop(stdscr, clients: list, rate: float, smoothing: bool, jitter: bool):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.noecho()

    state = ManualState(smoothing=smoothing, jitter=jitter)
    channels = state.channels()
    n_channels = len(channels)
    sel = 0

    targets_str = ", ".join(f"{c._address}:{c._port}" for c in clients)
    header = f"Manual Sensor Simulator   OSC -> {targets_str}  @ {rate:g} Hz"

    tick = 1.0 / rate
    start = time.monotonic()

    while True:
        now = time.monotonic()
        t = now - start

        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        sel_ch = channels[sel]
        if key in (ord("q"), 27):
            break
        elif key in (curses.KEY_LEFT, ord("h"), curses.KEY_UP, ord("k")):
            sel = (sel - 1) % n_channels
        elif key in (curses.KEY_RIGHT, ord("l"), curses.KEY_DOWN, ord("j")):
            sel = (sel + 1) % n_channels
        elif key in (ord("+"), ord("=")):
            state.adjust(sel_ch, STEP)
        elif key in (ord("-"), ord("_")):
            state.adjust(sel_ch, -STEP)
        elif key == ord("]"):
            state.adjust(sel_ch, FINE_STEP)
        elif key == ord("["):
            state.adjust(sel_ch, -FINE_STEP)
        elif key == ord(" "):
            state.set(sel_ch, 1.0)
        elif ord("0") <= key <= ord("9"):
            state.set(sel_ch, (key - ord("0")) / 10.0)
        elif key == ord("x"):
            state.toggle_mute(sel_ch)
        elif key == ord("t"):
            if sel_ch[0] == "pres":
                state.toggle_touch(sel_ch[1])
        elif key == ord("n"):
            if sel_ch[0] == "pres":
                state.set_node(sel_ch[1], 0.0)
        elif key == ord("m"):
            if sel_ch[0] == "pres":
                state.set_node(sel_ch[1], 1.0)
        elif key == ord("z"):
            state.zero_all()
        elif key == ord("f"):
            state.fill_all()
        elif key == ord("s"):
            state.smoothing = not state.smoothing
        elif key == ord("J"):
            state.jitter = not state.jitter

        state.update()
        state.send(clients, t)
        _draw(stdscr, state, sel, header)

        elapsed = time.monotonic() - now
        sleep_time = tick - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


def build_clients(args) -> list:
    if args.targets:
        clients = []
        for target in args.targets:
            host, port_str = target.rsplit(":", 1)
            clients.append(BroadcastUDPClient(host, int(port_str)))
        return clients
    return [SimpleUDPClient(args.host, args.port)]


def main():
    parser = argparse.ArgumentParser(
        description="Manually controllable OSC sensor simulator for the Shrine sound engine."
    )
    parser.add_argument("--host", default="127.0.0.1", help="OSC target host")
    parser.add_argument("--port", type=int, default=57120, help="OSC target port")
    parser.add_argument("--rate", type=float, default=30.0, help="Message send rate in Hz")
    parser.add_argument(
        "--no-smoothing",
        action="store_true",
        help="Start with smoothing off (channels snap to set values instantly)",
    )
    parser.add_argument(
        "--jitter",
        action="store_true",
        help="Start with organic jitter on (subtle noise layered on held values)",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        metavar="HOST:PORT",
        help="Send to multiple targets via broadcast UDP. Overrides --host/--port.",
    )
    args = parser.parse_args()

    clients = build_clients(args)
    curses.wrapper(_loop, clients, args.rate, not args.no_smoothing, args.jitter)
    sys.exit(0)


if __name__ == "__main__":
    main()
