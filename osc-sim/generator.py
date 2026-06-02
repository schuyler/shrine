#!/usr/bin/env python3
"""OSC sensor data simulator for testing the Shrine SuperCollider sound engine.

Generates synthetic capacitive and GSR sensor readings and streams them over
OSC to a SuperCollider instance. Supports named scenarios that play through
a creative arc of signal activity.

Usage:
    python osc-sim/generator.py [--host HOST] [--port PORT] [--rate HZ]
                                [--manual] [--scenario NAME]
"""

import argparse
import curses
import math
import socket
import sys
import time

from pythonosc.udp_client import SimpleUDPClient


class BroadcastUDPClient(SimpleUDPClient):
    """UDP client with SO_BROADCAST for sending to broadcast addresses."""

    def __init__(self, address: str, port: int):
        super().__init__(address, port)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# GSR pairs: all unique combinations of pads 1-4
GSR_PAIRS = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]

# Incommensurate frequencies for organic noise layering (Hz)
NOISE_FREQS = [0.1, 0.23, 0.37, 0.71]
NOISE_AMPS = [0.03, 0.025, 0.02, 0.02]


def cosine_interp(t: float) -> float:
    """Smooth S-curve interpolation over t in [0, 1].

    Returns values smoothly from 0.0 to 1.0 using a cosine shape,
    with near-zero derivative at both endpoints.
    """
    return 0.5 * (1.0 - math.cos(math.pi * t))


def layered_noise(t: float, channel_offset: float) -> float:
    """Additive organic noise from layered sine waves at incommensurate frequencies.

    Args:
        t: Current time in seconds.
        channel_offset: Per-channel phase offset to decorrelate channels.

    Returns:
        Noise value (unbounded; caller should clamp the result after adding).
    """
    value = 0.0
    for freq, amp in zip(NOISE_FREQS, NOISE_AMPS):
        value += amp * math.sin(2.0 * math.pi * freq * t + channel_offset)
    return value


class SignalChannel:
    """A single smoothed signal channel with organic noise.

    Maintains a current value that exponentially interpolates toward a target,
    with layered sine-wave noise added on top to simulate natural variation.
    """

    def __init__(self, smoothing_rate: float = 0.02, noise_offset: float = 0.0):
        """Initialize the channel.

        Args:
            smoothing_rate: Per-tick interpolation rate toward target (0-1).
            noise_offset: Phase offset for noise, used to decorrelate channels.
        """
        self.target = 0.0
        self.current = 0.0
        self.smoothing_rate = smoothing_rate
        self.noise_offset = noise_offset

    def update(self, t: float) -> float:
        """Advance the channel by one tick and return the current value.

        Args:
            t: Current time in seconds (used for noise generation).

        Returns:
            Current signal value clamped to [0.0, 1.0].
        """
        self.current += self.smoothing_rate * (self.target - self.current)
        noise = layered_noise(t, self.noise_offset)
        return max(0.0, min(1.0, self.current + noise))


# ---------------------------------------------------------------------------
# Phase definitions for the creative arc scenario
# ---------------------------------------------------------------------------

# Each phase is: (name, duration_seconds, cap, gsr_mag)
# cap: list of 4 floats indexed [pad1, pad2, pad3, pad4]
# gsr_mag: dict keyed by pair tuple, values are magnitudes [0, 1]

ARC_PHASES = [
    {
        "name": "Silence",
        "duration": 5.0,
        "cap": [0.0, 0.0, 0.0, 0.0],
        "gsr_mag": {p: 0.0 for p in GSR_PAIRS},
    },
    {
        "name": "Solo",
        "duration": 10.0,
        "cap": [0.7, 0.0, 0.0, 0.0],
        "gsr_mag": {p: 0.0 for p in GSR_PAIRS},
    },
    {
        "name": "Duo",
        "duration": 10.0,
        "cap": [0.7, 0.6, 0.0, 0.0],
        "gsr_mag": {
            (1, 2): 0.3,
            (1, 3): 0.0, (1, 4): 0.0,
            (2, 3): 0.0, (2, 4): 0.0,
            (3, 4): 0.0,
        },
    },
    {
        "name": "Trio",
        "duration": 10.0,
        "cap": [0.7, 0.6, 0.5, 0.0],
        "gsr_mag": {
            (1, 2): 0.3,
            (1, 3): 0.25, (1, 4): 0.0,
            (2, 3): 0.25, (2, 4): 0.0,
            (3, 4): 0.0,
        },
    },
    {
        "name": "Full",
        "duration": 10.0,
        "cap": [0.7, 0.6, 0.5, 0.5],
        "gsr_mag": {
            (1, 2): 0.3,
            (1, 3): 0.25, (1, 4): 0.2,
            (2, 3): 0.25, (2, 4): 0.2,
            (3, 4): 0.2,
        },
    },
    {
        "name": "Crescendo",
        "duration": 15.0,
        "cap": [1.0, 0.95, 0.9, 0.9],
        "gsr_mag": {
            (1, 2): 0.9,
            (1, 3): 0.8, (1, 4): 0.75,
            (2, 3): 0.8, (2, 4): 0.75,
            (3, 4): 0.7,
        },
    },
    {
        "name": "Decay",
        "duration": 10.0,
        "cap": [0.15, 0.1, 0.1, 0.1],
        "gsr_mag": {
            (1, 2): 0.2,
            (1, 3): 0.15, (1, 4): 0.1,
            (2, 3): 0.15, (2, 4): 0.1,
            (3, 4): 0.1,
        },
    },
]


class ArcScenario:
    """Drives the creative arc scenario through its defined phases.

    Cycles through all phases in order, using cosine interpolation to
    smoothly transition target values at each phase boundary.
    """

    def __init__(self):
        self.phase_index = 0
        self.phase_elapsed = 0.0
        self._phase_start_targets = self._snapshot_phase(0)

    def _snapshot_phase(self, index: int) -> dict:
        """Extract the flat target dict for a phase by index."""
        p = ARC_PHASES[index % len(ARC_PHASES)]
        targets = {}
        for i, v in enumerate(p["cap"]):
            targets[("cap", i + 1)] = v
        for pair, v in p["gsr_mag"].items():
            targets[("gsr_mag", pair)] = v
        return targets

    def update(self, dt: float) -> dict:
        """Advance the scenario clock and return interpolated targets.

        Args:
            dt: Elapsed time since last update in seconds.

        Returns:
            Dict mapping channel keys to interpolated target values.
        """
        self.phase_elapsed += dt
        phase = ARC_PHASES[self.phase_index]

        while self.phase_elapsed >= phase["duration"]:
            # Advance to next phase
            self.phase_elapsed -= phase["duration"]
            self._phase_start_targets = self._snapshot_phase(self.phase_index)
            self.phase_index = (self.phase_index + 1) % len(ARC_PHASES)
            phase = ARC_PHASES[self.phase_index]

        t = cosine_interp(self.phase_elapsed / phase["duration"])
        end_targets = self._snapshot_phase(self.phase_index)

        targets = {}
        for key, end_val in end_targets.items():
            start_val = self._phase_start_targets.get(key, 0.0)
            targets[key] = start_val + t * (end_val - start_val)
        return targets

    def phase_name(self) -> str:
        """Return the name of the current phase."""
        return ARC_PHASES[self.phase_index]["name"]


def build_channels(smoothing_rate: float = 0.02) -> dict:
    """Construct all SignalChannel instances with decorrelated noise offsets.

    Args:
        smoothing_rate: Per-tick interpolation rate toward target (0-1).

    Returns:
        Dict mapping channel keys to SignalChannel objects.
    """
    channels = {}
    offset = 0.0
    offset_step = 1.1  # Incommensurate offset to decorrelate channels

    for i in range(1, 5):
        channels[("cap", i)] = SignalChannel(smoothing_rate=smoothing_rate, noise_offset=offset)
        offset += offset_step

    for pair in GSR_PAIRS:
        channels[("gsr_mag", pair)] = SignalChannel(
            smoothing_rate=smoothing_rate, noise_offset=offset
        )
        offset += offset_step

    return channels


def send_osc(clients: list, channels: dict, t: float, noise: bool = True) -> dict:
    """Send all OSC messages for the current tick to all clients.

    Callers must call channel.update(t) for all channels before invoking this
    function. send_osc reads .current (post-noise value computed by update())
    rather than calling update() itself, to avoid double-updating channels.

    Args:
        clients: List of OSC UDP clients to send to.
        channels: Dict of channel keys to SignalChannel instances.
        t: Current time in seconds (used to compute noise-inclusive values).
        noise: If True, add organic noise on top of channel values.

    Returns:
        Dict mapping OSC address strings to the float values that were sent.
    """
    sent = {}

    def _val(key):
        v = channels[key].current
        if noise:
            v += layered_noise(t, channels[key].noise_offset)
        return max(0.0, min(1.0, v))

    for i in range(1, 5):
        val = _val(("cap", i))
        for client in clients:
            client.send_message(f"/pad/{i}/cap", float(val))
        sent[f"/pad/{i}/cap"] = val

    for pair in GSR_PAIRS:
        i, j = pair
        mag = _val(("gsr_mag", pair))

        for client in clients:
            client.send_message(f"/gsr/{i}/{j}", float(mag))
        sent[f"/gsr/{i}/{j}"] = mag

    return sent


def print_summary(sent: dict, scenario: ArcScenario, t: float):
    """Print a single-line summary of the values actually sent over OSC.

    Args:
        sent: Dict returned by send_osc mapping OSC addresses to sent values.
        scenario: Active scenario (for phase name).
        t: Current time in seconds.
    """
    caps = " ".join(f"{sent.get(f'/pad/{i}/cap', 0.0):.2f}" for i in range(1, 5))
    gsrs = " ".join(
        f"{sent.get(f'/gsr/{i}/{j}', 0.0):.2f}" for i, j in GSR_PAIRS
    )
    print(
        f"\r[{t:7.1f}s] {scenario.phase_name():12s} | cap: {caps} | gsr: {gsrs}",
        end="",
        flush=True,
    )


def run(clients: list, rate: float, scenario_name: str):
    """Main simulation loop.

    Args:
        clients: List of OSC UDP clients to send to.
        rate: Message send rate in Hz.
        scenario_name: Name of the scenario to run.
    """
    if scenario_name != "arc":
        print(f"Unknown scenario: {scenario_name!r}. Only 'arc' is supported.")
        sys.exit(1)

    channels = build_channels()
    scenario = ArcScenario()

    tick = 1.0 / rate
    start = time.monotonic()
    last = start

    targets_str = ", ".join(f"{c._address}:{c._port}" for c in clients)
    print(f"Sending OSC to {targets_str} at {rate} Hz. Ctrl-C to stop.")

    try:
        while True:
            now = time.monotonic()
            dt = now - last
            last = now
            t = now - start

            targets = scenario.update(dt)
            for key, val in targets.items():
                if key in channels:
                    channels[key].target = val

            for ch in channels.values():
                ch.update(t)

            sent = send_osc(clients, channels, t)
            print_summary(sent, scenario, t)

            elapsed = time.monotonic() - now
            sleep_time = tick - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print()  # Newline after the summary line


# ---------------------------------------------------------------------------
# Manual / TUI mode
# ---------------------------------------------------------------------------

# Channel order: 4 cap channels, then 6 GSR magnitude channels
MANUAL_CHANNELS = (
    [("cap", i) for i in range(1, 5)]
    + [("gsr_mag", p) for p in GSR_PAIRS]
)
MANUAL_LABELS = (
    [f"cap{i}" for i in range(1, 5)]
    + [f"gsr{''.join(str(x) for x in p)}" for p in GSR_PAIRS]
)

BAR_HEIGHT = 16  # Number of rows in the slider bar
STEP = 0.05       # Value change per keypress


def _draw_tui(stdscr, channels: dict, selected: int, targets_str: str):
    """Render the full TUI frame.

    Args:
        stdscr: curses window.
        channels: Dict of channel keys to SignalChannel instances.
        selected: Index of the currently selected channel.
        targets_str: Formatted string of all OSC targets (for header display).
    """
    stdscr.erase()
    max_rows, max_cols = stdscr.getmaxyx()

    n_channels = len(MANUAL_CHANNELS)
    col_width = 7  # characters per channel column

    # Header
    header = f"OSC -> {targets_str}  |  arrows: navigate/adjust  |  0: zero  f: fill  q: quit"
    try:
        stdscr.addstr(0, 0, header[:max_cols - 1], curses.A_BOLD)
    except curses.error:
        pass

    # Vertical layout: row 1 = group labels, row 2 = value, rows 3..BAR_HEIGHT+2 = bar, row BAR_HEIGHT+3 = label
    group_row = 1
    value_row = 3
    bar_top = 4
    bar_bottom = bar_top + BAR_HEIGHT - 1
    label_row = bar_bottom + 1

    # Group labels spanning the cap and gsr columns
    n_cap = 4
    cap_span = n_cap * col_width
    gsr_span = (n_channels - n_cap) * col_width
    try:
        stdscr.addstr(group_row, 0, "Capacitance".center(cap_span)[:cap_span], curses.A_UNDERLINE)
        stdscr.addstr(group_row, cap_span, "GSR Magnitude".center(gsr_span)[:gsr_span], curses.A_UNDERLINE)
    except curses.error:
        pass

    for idx, key in enumerate(MANUAL_CHANNELS):
        col = idx * col_width
        if col + col_width > max_cols:
            break

        ch = channels[key]
        val = max(0.0, min(1.0, ch.current))
        label = MANUAL_LABELS[idx]
        is_selected = (idx == selected)

        attr = curses.A_REVERSE if is_selected else curses.A_NORMAL

        # Value display
        value_str = f"{ch.target:.2f}"
        try:
            stdscr.addstr(value_row, col, value_str.center(col_width - 1), attr)
        except curses.error:
            pass

        # Bar: filled from bottom up
        filled_rows = round(val * BAR_HEIGHT)
        for row_offset in range(BAR_HEIGHT):
            # row_offset 0 = top of bar, BAR_HEIGHT-1 = bottom
            bar_row = bar_top + row_offset
            if bar_row >= max_rows - 1:
                break
            # Which rows are "filled" — the bottom `filled_rows` rows
            is_filled = row_offset >= (BAR_HEIGHT - filled_rows)
            char = "\u2588" if is_filled else "\u2591"  # █ or ░
            bar_attr = curses.A_REVERSE if is_selected else curses.A_NORMAL
            try:
                stdscr.addstr(bar_row, col, (char * (col_width - 1)), bar_attr)
            except curses.error:
                pass

        # Label
        if label_row < max_rows - 1:
            try:
                stdscr.addstr(label_row, col, label.center(col_width - 1), attr)
            except curses.error:
                pass

    stdscr.refresh()


def _manual_loop(stdscr, clients: list, rate: float):
    """Inner curses loop for manual mode.

    Args:
        stdscr: curses window provided by curses.wrapper.
        clients: List of OSC UDP clients to send to.
        rate: OSC send rate in Hz.
    """
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.noecho()

    channels = build_channels(smoothing_rate=0.15)

    # Manual mode: only cap and gsr_mag channels are user-controlled.

    targets_str = ", ".join(f"{c._address}:{c._port}" for c in clients)
    selected = 0
    n_channels = len(MANUAL_CHANNELS)
    tick = 1.0 / rate
    start = time.monotonic()

    while True:
        now = time.monotonic()
        t = now - start

        # Input
        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        if key == ord("q"):
            break
        elif key == ord("0"):
            for k in MANUAL_CHANNELS:
                channels[k].target = 0.0
        elif key == ord("f"):
            for k in MANUAL_CHANNELS:
                channels[k].target = 1.0
        elif key == curses.KEY_LEFT:
            selected = (selected - 1) % n_channels
        elif key == curses.KEY_RIGHT:
            selected = (selected + 1) % n_channels
        elif key == curses.KEY_UP:
            k = MANUAL_CHANNELS[selected]
            channels[k].target = min(1.0, channels[k].target + STEP)
        elif key == curses.KEY_DOWN:
            k = MANUAL_CHANNELS[selected]
            channels[k].target = max(0.0, channels[k].target - STEP)
        elif key == curses.KEY_RESIZE:
            pass  # erase/redraw on next frame handles resize

        # Update channel values (smoothing toward target)
        for key_ch in MANUAL_CHANNELS:
            channels[key_ch].update(t)

        # Send OSC (no organic noise in manual mode)
        send_osc(clients, channels, t, noise=False)

        # Draw
        _draw_tui(stdscr, channels, selected, targets_str)

        # Sleep for remaining tick time
        elapsed = time.monotonic() - now
        sleep_time = tick - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


def run_manual_mode(clients: list, rate: float):
    """Entry point for manual TUI mode.

    Args:
        clients: List of OSC UDP clients to send to.
        rate: OSC send rate in Hz.
    """
    curses.wrapper(_manual_loop, clients, rate)


def main():
    parser = argparse.ArgumentParser(
        description="OSC sensor data simulator for the Shrine sound engine."
    )
    parser.add_argument("--host", default="127.0.0.1", help="OSC target host")
    parser.add_argument("--port", type=int, default=57120, help="OSC target port")
    parser.add_argument(
        "--rate", type=float, default=30.0, help="Message send rate in Hz"
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Manual TUI mode with alsamixer-style sliders",
    )
    parser.add_argument(
        "--scenario",
        default="arc",
        help="Named scenario to run (default: arc)",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        metavar="HOST:PORT",
        help="Send to multiple targets (e.g., 255.255.255.255:57120 255.255.255.255:9000). "
             "Overrides --host/--port. Uses broadcast UDP.",
    )
    args = parser.parse_args()

    if args.targets:
        clients = []
        for target in args.targets:
            host, port_str = target.rsplit(":", 1)
            clients.append(BroadcastUDPClient(host, int(port_str)))
    else:
        clients = [SimpleUDPClient(args.host, args.port)]

    if args.manual:
        run_manual_mode(clients, args.rate)
        sys.exit(0)

    run(clients, args.rate, args.scenario)


if __name__ == "__main__":
    main()
