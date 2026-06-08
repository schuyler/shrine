#!/usr/bin/env python3
"""
Real-time FFT spectrum viewer for FDM diagnostic data.

Receives /shrine/node/{0-3}/fft OSC messages, each carrying a 1024-byte
blob of u8 log-magnitudes (0 = noise floor, 255 = full scale over 96 dB).

X-axis: frequency in Hz (bin index × sample_rate / FFT_N).
Y-axis: dB (u8 → 0..96 dB mapping).
Vertical lines mark auto-detected carrier peaks per node.

Usage:
    python scripts/plot_fft_osc.py
    python scripts/plot_fft_osc.py --port 9000
    python scripts/plot_fft_osc.py --sample-rate 180000

Requires: pip install pythonosc matplotlib numpy
"""

import argparse
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
NUM_NODES = 4
DEFAULT_SAMPLE_RATE = 180000

# Ignore bins below this frequency when searching for carrier peaks,
# to avoid locking onto DC offset or low-frequency noise.
PEAK_MIN_HZ = 5000

CARRIER_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231"]
SPECTRUM_COLOR = "#333333"

SMOOTH_KERNEL_SIZE = 15
DECIMATE_STRIDE = 4


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


def _find_carrier_peak(spectrum_db, freqs, min_hz):
    """Return the frequency of the strongest bin above min_hz."""
    min_bin = int(min_hz / (freqs[1] - freqs[0])) if len(freqs) > 1 else 0
    region = spectrum_db[min_bin:]
    if len(region) == 0:
        return None
    peak_bin = min_bin + np.argmax(region)
    return freqs[peak_bin]


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
    args = parser.parse_args()

    # Frequency axis: bin index × (sample_rate / FFT_N)
    freq_resolution = args.sample_rate / FFT_N
    freqs = np.arange(FFT_BINS) * freq_resolution
    freqs_decimated = freqs[::DECIMATE_STRIDE]

    # --- OSC server ---
    dispatcher = Dispatcher()
    for node_id in range(NUM_NODES):
        dispatcher.map(f"/shrine/node/{node_id}/fft", _make_fft_handler(node_id))

    server = BlockingOSCUDPServer((args.host, args.port), dispatcher)
    osc_thread = threading.Thread(target=server.serve_forever, daemon=True)
    osc_thread.start()
    print(f"Listening for FFT spectra on {args.host}:{args.port}")
    print(f"Frequency resolution: {freq_resolution:.1f} Hz/bin")
    print("Carrier markers: auto-detected from spectrum peaks")

    # --- Figure layout: 2×2 grid, one subplot per node ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True, sharey=True)
    fig.suptitle("FDM FFT Spectrum Diagnostic", fontsize=12)
    axes_flat = axes.flatten()

    lines = []
    carrier_lines = []  # one vline per node, updated each frame
    for node_id, ax in enumerate(axes_flat):
        ax.set_title(f"Node {node_id}", fontsize=10)
        ax.set_ylabel("dB")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylim(0, DB_RANGE)
        ax.set_xlim(freqs[0], 60000)
        ax.grid(True, alpha=0.3)

        (line,) = ax.plot(
            freqs_decimated, np.zeros(len(freqs_decimated)),
            color=SPECTRUM_COLOR, linewidth=1.5, alpha=0.8,
        )
        lines.append(line)

        # Carrier marker — starts invisible, positioned at 0
        vline = ax.axvline(
            0, color=CARRIER_COLORS[node_id], linewidth=1.5,
            linestyle="--", alpha=0.7, visible=False,
        )
        carrier_lines.append(vline)

    def _smooth_and_decimate(spectrum):
        """Moving-average smooth, then take every stride-th sample."""
        kernel = np.ones(SMOOTH_KERNEL_SIZE) / SMOOTH_KERNEL_SIZE
        smoothed = np.convolve(spectrum, kernel, mode="same")
        return smoothed[::DECIMATE_STRIDE]

    def update(_frame):
        with _lock:
            snapshot = dict(_spectra)

        for node_id, line in enumerate(lines):
            if node_id in snapshot:
                spectrum = snapshot[node_id]
                line.set_ydata(_smooth_and_decimate(spectrum))

                # Update carrier marker to strongest peak
                peak_hz = _find_carrier_peak(spectrum, freqs, PEAK_MIN_HZ)
                if peak_hz is not None:
                    seg = carrier_lines[node_id].get_paths()[0].vertices
                    seg[:, 0] = peak_hz
                    carrier_lines[node_id].set_visible(True)

        return lines + carrier_lines

    _ani = animation.FuncAnimation(
        fig, update, interval=200, blit=False, cache_frame_data=False,
    )
    plt.tight_layout()
    plt.show()
    server.shutdown()


if __name__ == "__main__":
    main()
