#!/usr/bin/env python3
"""
Real-time FFT spectrum viewer for FDM diagnostic data.

Receives /shrine/node/{0-3}/fft OSC messages, each carrying a 1024-byte
blob of u8 log-magnitudes (0 = noise floor, 255 = full scale over 96 dB).

X-axis: frequency in Hz (bin index × sample_rate / FFT_N).
Y-axis: dB (u8 → 0..96 dB mapping).
Vertical lines mark the 4 FDM carrier frequencies.

Usage:
    python scripts/plot_fft_osc.py
    python scripts/plot_fft_osc.py --port 9000
    python scripts/plot_fft_osc.py --sample-rate 180000

Requires: pip install pythonosc matplotlib numpy
"""

import argparse
import struct
import threading

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

# Defaults matching edge-node config.h
FFT_N = 2048
FFT_BINS = FFT_N // 2  # 1024
DB_RANGE = 96.0

# FDM carrier parameters (defaults from config.h)
DEFAULT_SAMPLE_RATE = 180000
DEFAULT_BASE_K = 180
DEFAULT_STEP_K = 20
DEFAULT_WINDOW_N = 1800
NUM_NODES = 4

CARRIER_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231"]
SPECTRUM_COLOR = "#333333"


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_spectra = {}  # node_id → numpy array of shape (FFT_BINS,) in dB


def _parse_fft_blob(osc_args):
    """Extract the u8 blob from OSC arguments.

    pythonosc delivers blob arguments as bytes objects.
    """
    for arg in osc_args:
        if isinstance(arg, (bytes, bytearray)):
            return arg
    return None


def _make_fft_handler(node_id: int):
    def handler(address, *args):
        blob = _parse_fft_blob(args)
        if blob is None or len(blob) < FFT_BINS:
            return
        # Convert u8 to dB: 0 → 0 dB, 255 → 96 dB
        spectrum_db = np.frombuffer(blob[:FFT_BINS], dtype=np.uint8).astype(
            np.float32
        ) * (DB_RANGE / 255.0)
        with _lock:
            _spectra[node_id] = spectrum_db

    return handler


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Real-time FFT spectrum viewer for FDM diagnostics."
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="OSC listen address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=57120, help="OSC listen port (default: 57120)"
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help=f"ADC sample rate in Hz (default: {DEFAULT_SAMPLE_RATE})",
    )
    parser.add_argument(
        "--base-k",
        type=int,
        default=DEFAULT_BASE_K,
        help=f"DFT bin for node 0 (default: {DEFAULT_BASE_K})",
    )
    parser.add_argument(
        "--step-k",
        type=int,
        default=DEFAULT_STEP_K,
        help=f"Bin spacing between nodes (default: {DEFAULT_STEP_K})",
    )
    parser.add_argument(
        "--window-n",
        type=int,
        default=DEFAULT_WINDOW_N,
        help=f"Samples per demod window (default: {DEFAULT_WINDOW_N})",
    )
    args = parser.parse_args()

    # Frequency axis: bin index × (sample_rate / FFT_N)
    freq_resolution = args.sample_rate / FFT_N
    freqs = np.arange(FFT_BINS) * freq_resolution

    # Carrier frequencies
    carrier_freqs = []
    for node_id in range(NUM_NODES):
        k = args.base_k + node_id * args.step_k
        f = k * args.sample_rate / args.window_n
        carrier_freqs.append(f)

    # --- OSC server ---
    dispatcher = Dispatcher()
    for node_id in range(NUM_NODES):
        dispatcher.map(f"/shrine/node/{node_id}/fft", _make_fft_handler(node_id))

    server = BlockingOSCUDPServer((args.host, args.port), dispatcher)
    osc_thread = threading.Thread(target=server.serve_forever, daemon=True)
    osc_thread.start()
    print(f"Listening for FFT spectra on {args.host}:{args.port}")
    print(f"Frequency resolution: {freq_resolution:.1f} Hz/bin")
    for nid, cf in enumerate(carrier_freqs):
        print(f"  Node {nid} carrier: {cf:.0f} Hz (k={args.base_k + nid * args.step_k})")

    # --- Figure layout: 2×2 grid, one subplot per node ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True, sharey=True)
    fig.suptitle("FDM FFT Spectrum Diagnostic", fontsize=12)
    axes_flat = axes.flatten()

    bars = []
    for node_id, ax in enumerate(axes_flat):
        ax.set_title(f"Node {node_id}", fontsize=10)
        ax.set_ylabel("dB")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylim(0, DB_RANGE)
        ax.set_xlim(freqs[0], freqs[-1])
        ax.grid(True, alpha=0.3)

        # Spectrum line
        (line,) = ax.plot(freqs, np.zeros(FFT_BINS), color=SPECTRUM_COLOR,
                          linewidth=0.5, alpha=0.8)
        bars.append(line)

        # Carrier frequency markers
        for nid, cf in enumerate(carrier_freqs):
            ax.axvline(cf, color=CARRIER_COLORS[nid], linewidth=1.0,
                       linestyle="--", alpha=0.7,
                       label=f"N{nid} {cf:.0f} Hz" if node_id == 0 else None)

    axes_flat[0].legend(loc="upper right", fontsize=7)

    def update(_frame):
        with _lock:
            snapshot = dict(_spectra)

        for node_id, line in enumerate(bars):
            if node_id in snapshot:
                line.set_ydata(snapshot[node_id])

        return bars

    _ani = animation.FuncAnimation(
        fig, update, interval=200, blit=False, cache_frame_data=False
    )
    plt.tight_layout()
    plt.show()
    server.shutdown()


if __name__ == "__main__":
    main()
