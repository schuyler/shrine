#!/usr/bin/env python3
"""
Real-time OSC diagnostic plotter for the 4-node FDM system.

Receives /shrine/node/{0-3} OSC messages, each carrying 5 floats:
    (self_stdev, self_carrier_mag, gsr_mag[0], gsr_mag[1], gsr_mag[2])

Layout (GridSpec 3×2):
    Row 0 (full width): 6 pairwise I/Q magnitudes
    Rows 1-2 (2×2 grid): per-node stdev (node 0–3)

Pair mapping (0-indexed):
    6 pairs: (0,1), (0,2), (0,3), (1,2), (1,3), (2,3)
    Node 0 GSR slots → global pair indices [0, 1, 2]
    Node 1 GSR slots → global pair indices [3, 4, 0]
    Node 2 GSR slots → global pair indices [5, 1, 3]
    Node 3 GSR slots → global pair indices [2, 4, 5]

Each pair is observed from both sides; latest value wins.

Usage:
    python fdm-bench/plot_fdm_osc.py
    python fdm-bench/plot_fdm_osc.py --port 9000
    python fdm-bench/plot_fdm_osc.py --host 0.0.0.0 --port 57120

Requires: pip install pythonosc matplotlib numpy scipy
"""

import argparse
import threading
import time
from collections import deque

import numpy as np
from scipy.interpolate import make_interp_spline
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from leds.sensor_state import GSR_PAIRS, NODE_GSR_MAPPING

DISPLAY_SECONDS = 10   # visible time window
HISTORY = 1500         # sample buffer per channel
EMA_TAU = 0.3          # EMA time constant in seconds
INTERP_FACTOR = 3      # spline densification for smooth peaks

PAIR_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4"]
PAIR_LABELS = [f"({i},{j})" for i, j in GSR_PAIRS]

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_lock = threading.Lock()

# Per-node: deques of (timestamp, ema_value) for stdev
_node_ts = [deque(maxlen=HISTORY) for _ in range(4)]
_node_sd = [deque(maxlen=HISTORY) for _ in range(4)]
_node_ema_sd = [None] * 4
_node_last_t = [None] * 4

# Per-pair: deques of (timestamp, ema_value) for GSR magnitude
_pair_ts = [deque(maxlen=HISTORY) for _ in range(6)]
_pair_mag = [deque(maxlen=HISTORY) for _ in range(6)]
_pair_ema_mag = [None] * 6
_pair_last_t = [None] * 6

_t0 = None


def _ema_alpha(dt: float) -> float:
    return min(1.0, dt / (EMA_TAU + dt)) if dt > 0 else 1.0


def _make_node_handler(node_id: int):
    def handler(address, stdev, carrier_mag, m0, m1, m2, *args):
        t = time.time() - _t0
        with _lock:
            # --- stdev EMA ---
            dt = (t - _node_last_t[node_id]) if _node_last_t[node_id] is not None else 0.0
            _node_last_t[node_id] = t
            alpha = _ema_alpha(dt)
            if _node_ema_sd[node_id] is None:
                _node_ema_sd[node_id] = stdev
            else:
                _node_ema_sd[node_id] += alpha * (stdev - _node_ema_sd[node_id])
            _node_ts[node_id].append(t)
            _node_sd[node_id].append(_node_ema_sd[node_id])

            # --- GSR magnitude EMA (3 slots) ---
            local_mags = [m0, m1, m2]
            for local_idx, global_idx in enumerate(NODE_GSR_MAPPING[node_id]):
                raw = local_mags[local_idx]
                dt_p = (t - _pair_last_t[global_idx]) if _pair_last_t[global_idx] is not None else 0.0
                _pair_last_t[global_idx] = t
                alpha_p = _ema_alpha(dt_p)
                if _pair_ema_mag[global_idx] is None:
                    _pair_ema_mag[global_idx] = raw
                else:
                    _pair_ema_mag[global_idx] += alpha_p * (raw - _pair_ema_mag[global_idx])
                _pair_ts[global_idx].append(t)
                _pair_mag[global_idx].append(_pair_ema_mag[global_idx])

    return handler


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _spline_xy(t_arr, v_arr):
    """Return (t_dense, v_spline) for rendering, or None if too few points."""
    if len(t_arr) < 2:
        return None
    k = min(3, len(t_arr) - 1)
    t_dense = np.linspace(t_arr[0], t_arr[-1], len(t_arr) * INTERP_FACTOR)
    spline = make_interp_spline(t_arr, v_arr, k=k)
    return t_dense, spline(t_dense)


def _trim(ts_dq, val_dq, t_cutoff):
    """Return numpy arrays for ts/vals trimmed to [t_cutoff, now]."""
    t_arr = np.array(list(ts_dq))
    v_arr = np.array(list(val_dq))
    if len(t_arr) == 0:
        return t_arr, v_arr
    mask = t_arr >= t_cutoff
    return t_arr[mask], v_arr[mask]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Real-time OSC plotter for 4-node FDM system.")
    parser.add_argument("--host", default="0.0.0.0", help="OSC listen address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=57120, help="OSC listen port (default: 57120)")
    args = parser.parse_args()

    # --- OSC server ---
    dispatcher = Dispatcher()
    for node_id in range(4):
        dispatcher.map(f"/shrine/node/{node_id}", _make_node_handler(node_id))

    server = BlockingOSCUDPServer((args.host, args.port), dispatcher)

    global _t0
    _t0 = time.time()

    osc_thread = threading.Thread(target=server.serve_forever, daemon=True)
    osc_thread.start()
    print(f"Listening for OSC on {args.host}:{args.port}")

    # --- Figure layout ---
    fig = plt.figure(figsize=(12, 8))
    fig.suptitle("FDM OSC — Pairwise Magnitudes & Per-Node Stdev", fontsize=12)
    gs = fig.add_gridspec(3, 2, hspace=0.45, wspace=0.3)

    ax_pairs = fig.add_subplot(gs[0, :])
    ax_pairs.set_ylabel("GSR Magnitude")
    ax_pairs.set_xlabel("Time (s)")
    ax_pairs.grid(True, alpha=0.3)
    ax_pairs.set_title("Pairwise I/Q Magnitudes")

    pair_lines = []
    for i, (color, label) in enumerate(zip(PAIR_COLORS, PAIR_LABELS)):
        (ln,) = ax_pairs.plot([], [], color=color, linewidth=1.5, label=label)
        pair_lines.append(ln)
    ax_pairs.legend(loc="upper left", fontsize=8, ncol=3)

    node_axes = []
    node_lines = []
    node_positions = [(1, 0), (1, 1), (2, 0), (2, 1)]
    for node_id, (row, col) in enumerate(node_positions):
        ax = fig.add_subplot(gs[row, col])
        ax.set_title(f"Node {node_id} — Stdev", fontsize=9)
        ax.set_ylabel("Stdev")
        ax.set_xlabel("Time (s)")
        ax.grid(True, alpha=0.3)
        (ln,) = ax.plot([], [], color=PAIR_COLORS[node_id], linewidth=1.5)
        node_axes.append(ax)
        node_lines.append(ln)

    # Running y-range accumulators (expand-only, like plot_fdm.py)
    pair_y = [[float("inf"), float("-inf")] for _ in range(6)]
    node_y = [[float("inf"), float("-inf")] for _ in range(4)]

    def update(_frame):
        now = time.time() - _t0
        t_cutoff = now - DISPLAY_SECONDS

        with _lock:
            # Snapshot to avoid holding the lock during rendering
            p_ts = [list(q) for q in _pair_ts]
            p_mag = [list(q) for q in _pair_mag]
            n_ts = [list(q) for q in _node_ts]
            n_sd = [list(q) for q in _node_sd]

        # --- Pair magnitude plots ---
        t_min_pairs = float("inf")
        t_max_pairs = float("-inf")
        for i in range(6):
            t_arr, v_arr = _trim(p_ts[i], p_mag[i], t_cutoff)
            if len(t_arr) < 2:
                pair_lines[i].set_data([], [])
                continue
            result = _spline_xy(t_arr, v_arr)
            if result is None:
                pair_lines[i].set_data([], [])
                continue
            t_dense, v_dense = result
            pair_lines[i].set_data(t_dense, v_dense)
            t_min_pairs = min(t_min_pairs, t_arr[0])
            t_max_pairs = max(t_max_pairs, t_arr[-1])
            lo, hi = pair_y[i]
            pair_y[i] = [min(lo, v_arr.min()), max(hi, v_arr.max())]

        if t_max_pairs > t_min_pairs:
            ax_pairs.set_xlim(t_min_pairs, t_max_pairs)
            all_lo = min(r[0] for r in pair_y if r[0] != float("inf"))
            all_hi = max(r[1] for r in pair_y if r[1] != float("-inf"))
            if all_hi > all_lo:
                margin = (all_hi - all_lo) * 0.05
            else:
                margin = 1.0
            ax_pairs.set_ylim(all_lo - margin, all_hi + margin)

        # --- Per-node stdev plots ---
        for node_id in range(4):
            ax = node_axes[node_id]
            ln = node_lines[node_id]
            t_arr, v_arr = _trim(n_ts[node_id], n_sd[node_id], t_cutoff)
            if len(t_arr) < 2:
                ln.set_data([], [])
                continue
            result = _spline_xy(t_arr, v_arr)
            if result is None:
                ln.set_data([], [])
                continue
            t_dense, v_dense = result
            ln.set_data(t_dense, v_dense)
            ax.set_xlim(t_arr[0], t_arr[-1])
            lo, hi = node_y[node_id]
            lo = min(lo, v_arr.min())
            hi = max(hi, v_arr.max())
            node_y[node_id] = [lo, hi]
            margin = (hi - lo) * 0.05 if hi > lo else 1.0
            ax.set_ylim(lo - margin, hi + margin)

        return pair_lines + node_lines

    ani = animation.FuncAnimation(
        fig, update, interval=50, blit=False, cache_frame_data=False
    )
    plt.tight_layout()
    plt.show()
    server.shutdown()


if __name__ == "__main__":
    main()
