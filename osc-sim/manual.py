#!/usr/bin/env python3
"""Manually controllable OSC sensor simulator for the Shrine sound engine.

Unlike ``generator.py``, which plays an automated scenario, this tool puts
every channel under direct keyboard control. It mirrors the firmware's actual
OSC output exactly: for each of the four nodes it streams ``/shrine/node/N``
with five floats — ``self_stdev``, ``self_carrier_mag`` and three ``gsr_mag``
cross-couplings (see edge-node/README.md, "OSC Output"). Every one of those 20
floats is an independent slider, so you can pose any sensor state by hand and
hold it for as long as you like.

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
    t               touch / release the selected node (mute all its channels)
    n / m           zero / max the whole selected node
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

# Reuse the broadcast client and noise generator from the automated simulator
# so both tools share a single source of truth for those behaviours.
from generator import BroadcastUDPClient, layered_noise

NUM_NODES = 4

# Per-node OSC floats, in the exact order the firmware sends them.
# (label shown in the UI, short tag used in status text)
NODE_CHANNELS = (
    ("stdev", "stdev"),
    ("carrier", "carr"),
    ("gsr0", "gsr0"),
    ("gsr1", "gsr1"),
    ("gsr2", "gsr2"),
)
NUM_CHANNELS = len(NODE_CHANNELS)

STEP = 0.05          # coarse adjust per keypress
FINE_STEP = 0.01     # fine adjust per keypress
SMOOTHING_RATE = 0.2  # per-tick easing toward target when smoothing is on
BAR_WIDTH = 8        # filled-bar width in characters


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class ManualState:
    """The 20-channel grid the user drives, independent of any UI.

    Each channel tracks a ``target`` (what the user dialled in) and a
    ``current`` value that is sent over OSC. With smoothing enabled, ``current``
    eases toward ``target`` each tick; otherwise it snaps immediately. Optional
    jitter layers organic noise on top of the sent value without disturbing the
    target, so the held pose is preserved.
    """

    def __init__(self, smoothing: bool = True, jitter: bool = False):
        # Row-major grids indexed [node][channel].
        self.target = [[0.0] * NUM_CHANNELS for _ in range(NUM_NODES)]
        self.current = [[0.0] * NUM_CHANNELS for _ in range(NUM_NODES)]
        # Mute is a non-destructive layer: a muted channel sends 0.0 but keeps
        # its target, so "release" then "touch" restores the held pose.
        self.muted = [[False] * NUM_CHANNELS for _ in range(NUM_NODES)]
        self.smoothing = smoothing
        self.jitter = jitter

    def set(self, node: int, ch: int, value: float) -> None:
        self.target[node][ch] = _clamp(value)

    def adjust(self, node: int, ch: int, delta: float) -> None:
        self.set(node, ch, self.target[node][ch] + delta)

    def zero_all(self) -> None:
        for n in range(NUM_NODES):
            for c in range(NUM_CHANNELS):
                self.target[n][c] = 0.0

    def fill_all(self) -> None:
        for n in range(NUM_NODES):
            for c in range(NUM_CHANNELS):
                self.target[n][c] = 1.0

    def set_node(self, node: int, value: float) -> None:
        for c in range(NUM_CHANNELS):
            self.target[node][c] = _clamp(value)

    def toggle_mute(self, node: int, ch: int) -> None:
        self.muted[node][ch] = not self.muted[node][ch]

    def node_released(self, node: int) -> bool:
        """True when every channel of a node is muted (the user has let go)."""
        return all(self.muted[node])

    def toggle_touch(self, node: int) -> None:
        """Touch or release a whole user: unmute all if released, else mute all."""
        release = not self.node_released(node)
        for c in range(NUM_CHANNELS):
            self.muted[node][c] = release

    def update(self) -> None:
        """Advance every channel one tick toward its target."""
        for n in range(NUM_NODES):
            for c in range(NUM_CHANNELS):
                if self.smoothing:
                    cur = self.current[n][c]
                    self.current[n][c] = cur + SMOOTHING_RATE * (self.target[n][c] - cur)
                else:
                    self.current[n][c] = self.target[n][c]

    def payloads(self, t: float) -> dict:
        """Build the OSC payload for each node from the current values.

        Args:
            t: Current time in seconds, used for jitter when enabled.

        Returns:
            Dict mapping ``/shrine/node/N`` to its list of five floats.
        """
        sent = {}
        for n in range(NUM_NODES):
            args = []
            for c in range(NUM_CHANNELS):
                if self.muted[n][c]:
                    args.append(0.0)
                    continue
                v = self.current[n][c]
                if self.jitter:
                    # Decorrelate channels with a per-cell phase offset.
                    v += layered_noise(t, (n * NUM_CHANNELS + c) * 1.1)
                args.append(_clamp(v))
            sent[f"/shrine/node/{n}"] = args
        return sent

    def send(self, clients: list, t: float) -> dict:
        """Send the current payload to every client and return what was sent."""
        sent = self.payloads(t)
        for address, args in sent.items():
            for client in clients:
                client.send_message(address, args)
        return sent


# ---------------------------------------------------------------------------
# Curses TUI
# ---------------------------------------------------------------------------

LABEL_W = 9   # left-hand channel-label column
CELL_W = 16   # per-node column: "[████░░░░] 0.55 "


def _draw(stdscr, state: ManualState, sel_node: int, sel_ch: int, header: str):
    stdscr.erase()
    max_rows, max_cols = stdscr.getmaxyx()

    def put(row, col, text, attr=curses.A_NORMAL):
        if row >= max_rows or col >= max_cols:
            return
        try:
            stdscr.addstr(row, col, text[: max_cols - col - 1], attr)
        except curses.error:
            pass

    put(0, 0, header, curses.A_BOLD)

    flags = f"smoothing:{'on' if state.smoothing else 'off'}  jitter:{'on' if state.jitter else 'off'}"
    put(1, 0, flags, curses.A_DIM)

    # Node header row.
    node_row = 3
    for n in range(NUM_NODES):
        col = LABEL_W + n * CELL_W
        attr = curses.A_BOLD | (curses.A_REVERSE if n == sel_node else 0)
        label = f"node{n} rel" if state.node_released(n) else f"node{n}"
        put(node_row, col, label.center(CELL_W - 1), attr)

    # Channel rows.
    for c, (label, _tag) in enumerate(NODE_CHANNELS):
        row = node_row + 1 + c
        put(row, 0, label.rjust(LABEL_W - 1))
        for n in range(NUM_NODES):
            col = LABEL_W + n * CELL_W
            val = _clamp(state.current[n][c])
            filled = round(val * BAR_WIDTH)
            bar = "█" * filled + "░" * (BAR_WIDTH - filled)
            muted = state.muted[n][c]
            is_sel = (n == sel_node and c == sel_ch)
            # Muted cells show the held level greyed out with a "mute" tag, so
            # the dialed-in pose stays visible while output is suppressed.
            cell = f"[{bar}] {'mute' if muted else f'{state.target[n][c]:.2f}'}"
            if is_sel:
                attr = curses.A_REVERSE
            elif muted:
                attr = curses.A_DIM
            else:
                attr = curses.A_NORMAL
            put(row, col, cell, attr)

    # Status + help.
    status_row = node_row + 1 + NUM_CHANNELS + 1
    sel_label = NODE_CHANNELS[sel_ch][0]
    sel_state = "muted" if state.muted[sel_node][sel_ch] else f"{state.target[sel_node][sel_ch]:.2f}"
    put(
        status_row,
        0,
        f"selected: node{sel_node} / {sel_label} = {sel_state}   step {STEP:.2f}",
        curses.A_BOLD,
    )
    put(
        status_row + 2,
        0,
        "arrows/hjkl move  +/- adjust  ]/[ fine  0-9 set  space=1.0",
        curses.A_DIM,
    )
    put(
        status_row + 3,
        0,
        "x mute chan  t touch/release node  n/m zero/max node  z/f zero/fill all",
        curses.A_DIM,
    )
    put(
        status_row + 4,
        0,
        "s smooth  J jitter  q quit",
        curses.A_DIM,
    )

    stdscr.refresh()


def _loop(stdscr, clients: list, rate: float, smoothing: bool, jitter: bool):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.noecho()

    state = ManualState(smoothing=smoothing, jitter=jitter)
    sel_node = 0
    sel_ch = 0

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

        if key in (ord("q"), 27):  # q or ESC
            break
        elif key in (curses.KEY_LEFT, ord("h")):
            sel_node = (sel_node - 1) % NUM_NODES
        elif key in (curses.KEY_RIGHT, ord("l")):
            sel_node = (sel_node + 1) % NUM_NODES
        elif key in (curses.KEY_UP, ord("k")):
            sel_ch = (sel_ch - 1) % NUM_CHANNELS
        elif key in (curses.KEY_DOWN, ord("j")):
            sel_ch = (sel_ch + 1) % NUM_CHANNELS
        elif key in (ord("+"), ord("=")):
            state.adjust(sel_node, sel_ch, STEP)
        elif key in (ord("-"), ord("_")):
            state.adjust(sel_node, sel_ch, -STEP)
        elif key == ord("]"):
            state.adjust(sel_node, sel_ch, FINE_STEP)
        elif key == ord("["):
            state.adjust(sel_node, sel_ch, -FINE_STEP)
        elif key == ord(" "):
            state.set(sel_node, sel_ch, 1.0)
        elif ord("0") <= key <= ord("9"):
            state.set(sel_node, sel_ch, (key - ord("0")) / 10.0)
        elif key == ord("x"):
            state.toggle_mute(sel_node, sel_ch)
        elif key == ord("t"):
            state.toggle_touch(sel_node)
        elif key == ord("n"):
            state.set_node(sel_node, 0.0)
        elif key == ord("m"):
            state.set_node(sel_node, 1.0)
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
        _draw(stdscr, state, sel_node, sel_ch, header)

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
    curses.wrapper(
        _loop, clients, args.rate, not args.no_smoothing, args.jitter
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
