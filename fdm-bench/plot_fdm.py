#!/usr/bin/env python3
"""
Real-time plot of FDM bench continuous output.

Reads serial output lines of the form:
    mag=XXX.X sd=XXX mean=XXXX n=1800

Plots magnitude and stdev vs. time in two subplots.
Samples are decimated to ~44 Hz (every 4th line) and filtered with a short
EMA (τ=0.3 s) for noise reduction with minimal lag.

Usage:
    python plot_fdm.py /dev/ttyUSB0        # Linux
    python plot_fdm.py /dev/cu.usbserial-* # macOS
    python plot_fdm.py COM3                # Windows

Requires: pip install pyserial matplotlib numpy scipy
"""

import sys
import re
import time
from collections import deque

import numpy as np
from scipy.interpolate import make_interp_spline
import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

BAUD = 115200
DECIMATE_N = 4       # keep every Nth serial line (~44 Hz from ~176 Hz firmware)
DISPLAY_SECONDS = 10 # visible time window
HISTORY = 1000       # sample buffer (oversized to ensure 10 s coverage)
EMA_TAU = 0.3        # EMA time constant in seconds (signal smoothing)
INTERP_FACTOR = 3    # spline densification for rounded peaks

PAT = re.compile(
    r"mag=([\d.]+)\s+sd=([\d.]+)\s+mean=([\d.]+)\s+n=(\d+)"
)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <serial-port>", file=sys.stderr)
        sys.exit(1)

    port = serial.Serial(sys.argv[1], BAUD, timeout=0.05)

    ts = deque(maxlen=HISTORY)
    mags = deque(maxlen=HISTORY)
    sds = deque(maxlen=HISTORY)
    t0 = time.time()
    sample_count = 0  # counter for decimation
    last_t = None     # timestamp of previous stored sample

    # EMA state — initialized on first sample
    ema_mag = None
    ema_sd = None

    fig, (ax_mag, ax_sd) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.suptitle("FDM Bench — Magnitude & Stdev", fontsize=12)

    (line_mag,) = ax_mag.plot([], [], "b-", linewidth=2)
    ax_mag.set_ylabel("Magnitude")
    ax_mag.grid(True, alpha=0.3)

    (line_sd,) = ax_sd.plot([], [], "g-", linewidth=2)
    ax_sd.set_ylabel("Stdev")
    ax_sd.set_xlabel("Time (s)")
    ax_sd.grid(True, alpha=0.3)

    y_ranges = {ax: [float('inf'), float('-inf')] for ax in (ax_mag, ax_sd)}

    def update(_frame):
        nonlocal sample_count, last_t, ema_mag, ema_sd
        while port.in_waiting:
            try:
                line = port.readline().decode("ascii", errors="replace").strip()
            except Exception:
                continue
            m = PAT.search(line)
            if not m:
                continue
            sample_count += 1
            if sample_count % DECIMATE_N != 0:
                continue
            t = time.time() - t0

            raw_mag = float(m.group(1))
            raw_sd = float(m.group(2))

            # EMA: α = dt / (τ + dt)
            dt = (t - last_t) if last_t is not None else 0.0
            last_t = t
            alpha = min(1.0, dt / (EMA_TAU + dt)) if dt > 0 else 1.0

            if ema_mag is None:
                ema_mag = raw_mag
                ema_sd = raw_sd
            else:
                ema_mag += alpha * (raw_mag - ema_mag)
                ema_sd += alpha * (raw_sd - ema_sd)

            ts.append(t)
            mags.append(ema_mag)
            sds.append(ema_sd)

        if len(ts) < 2:
            return line_mag, line_sd

        t_arr = np.array(list(ts))

        # Trim to visible time window
        t_cutoff = t_arr[-1] - DISPLAY_SECONDS
        mask = t_arr >= t_cutoff
        t_arr = t_arr[mask]
        mag_arr = np.array(list(mags))[mask]
        sd_arr = np.array(list(sds))[mask]

        # Cubic spline to round off peaks
        t_dense = np.linspace(t_arr[0], t_arr[-1], len(t_arr) * INTERP_FACTOR)
        k = min(3, len(t_arr) - 1)
        for line_obj, arr in [(line_mag, mag_arr), (line_sd, sd_arr)]:
            spline = make_interp_spline(t_arr, arr, k=k)
            line_obj.set_data(t_dense, spline(t_dense))

        for ax, arr in [(ax_mag, mag_arr), (ax_sd, sd_arr)]:
            ax.set_xlim(t_arr[0], t_arr[-1])
            lo, hi = y_ranges[ax]
            lo = min(lo, arr.min())
            hi = max(hi, arr.max())
            y_ranges[ax] = [lo, hi]
            margin = (hi - lo) * 0.05 if hi > lo else 1.0
            ax.set_ylim(lo - margin, hi + margin)

        return line_mag, line_sd

    ani = animation.FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    plt.tight_layout()
    plt.show()
    port.close()


if __name__ == "__main__":
    main()
