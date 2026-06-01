#!/usr/bin/env python3
"""
Real-time plot of I/Q demodulation output from cap-demo GSR RX mode.

Reads serial output lines of the form:
    mag=421.1 phase=-81.5 sd=811 mean=1741 n=1024

Plots magnitude, phase, and stdev vs. time in three subplots.
Samples are decimated to ~44 Hz (every 4th line from ~176 Hz firmware)
and filtered with a short EMA (τ=0.3 s) for noise reduction with minimal
lag.  Phase is unwrapped and detrended to remove the ~6°/s clock drift,
isolating contact-related shifts.

Usage:
    python plot_iq.py /dev/ttyUSB0        # Linux
    python plot_iq.py /dev/cu.usbserial-* # macOS
    python plot_iq.py COM3                # Windows

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
EMA_TAU = 0.3        # EMA time constant in seconds
INTERP_FACTOR = 3    # spline densification for rounded peaks

PAT = re.compile(
    r"mag=([\d.]+)\s+phase=([-\d.]+)\s+sd=([\d.]+)\s+mean=([\d.]+)"
)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <serial-port>", file=sys.stderr)
        sys.exit(1)

    port = serial.Serial(sys.argv[1], BAUD, timeout=0.05)

    ts = deque(maxlen=HISTORY)
    mags = deque(maxlen=HISTORY)
    phases = deque(maxlen=HISTORY)
    sds = deque(maxlen=HISTORY)
    t0 = time.time()
    sample_count = 0  # counter for decimation
    last_t = None     # timestamp of previous stored sample

    # EMA state — initialized on first sample
    ema_mag = None
    ema_phase = None
    ema_sd = None

    fig, (ax_mag, ax_phase, ax_sd) = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    fig.suptitle("I/Q Demodulation — GSR RX", fontsize=12)

    (line_mag,) = ax_mag.plot([], [], "b-", linewidth=2)
    ax_mag.set_ylabel("Magnitude")
    ax_mag.grid(True, alpha=0.3)

    (line_phase,) = ax_phase.plot([], [], "r-", linewidth=2)
    ax_phase.set_ylabel("Phase °")
    ax_phase.grid(True, alpha=0.3)

    (line_sd,) = ax_sd.plot([], [], "g-", linewidth=2)
    ax_sd.set_ylabel("Stdev")
    ax_sd.set_xlabel("Time (s)")
    ax_sd.grid(True, alpha=0.3)

    y_ranges = {ax: [float('inf'), float('-inf')] for ax in (ax_mag, ax_phase, ax_sd)}

    def update(_frame):
        nonlocal sample_count, last_t, ema_mag, ema_phase, ema_sd
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
            raw_phase = float(m.group(2))
            raw_sd = float(m.group(3))

            # EMA: α = dt / (τ + dt)
            dt = (t - last_t) if last_t is not None else 0.0
            last_t = t
            alpha = min(1.0, dt / (EMA_TAU + dt)) if dt > 0 else 1.0

            if ema_mag is None:
                ema_mag = raw_mag
                ema_phase = raw_phase
                ema_sd = raw_sd
            else:
                ema_mag += alpha * (raw_mag - ema_mag)
                ema_phase += alpha * (raw_phase - ema_phase)
                ema_sd += alpha * (raw_sd - ema_sd)

            ts.append(t)
            mags.append(ema_mag)
            phases.append(ema_phase)
            sds.append(ema_sd)

        if len(ts) < 2:
            return line_mag, line_phase, line_sd

        t_arr = np.array(list(ts))

        # Trim to visible time window
        t_cutoff = t_arr[-1] - DISPLAY_SECONDS
        mask = t_arr >= t_cutoff
        t_arr = t_arr[mask]
        mag_arr = np.array(list(mags))[mask]
        sd_arr = np.array(list(sds))[mask]

        # Unwrap phase and remove linear drift
        phase_unwrapped = np.degrees(np.unwrap(np.radians(list(phases))))[mask]
        if len(t_arr) >= 2:
            # Linear fit to remove ~6°/s clock drift
            coeffs = np.polyfit(t_arr, phase_unwrapped, 1)
            phase_detrended = phase_unwrapped - np.polyval(coeffs, t_arr)
        else:
            phase_detrended = phase_unwrapped

        # Cubic spline to round off peaks
        t_dense = np.linspace(t_arr[0], t_arr[-1], len(t_arr) * INTERP_FACTOR)
        k = min(3, len(t_arr) - 1)
        for line_obj, arr in [(line_mag, mag_arr), (line_phase, phase_detrended), (line_sd, sd_arr)]:
            spline = make_interp_spline(t_arr, arr, k=k)
            line_obj.set_data(t_dense, spline(t_dense))

        for ax, arr in [(ax_mag, mag_arr), (ax_phase, phase_detrended), (ax_sd, sd_arr)]:
            ax.set_xlim(t_arr[0], t_arr[-1])
            lo, hi = y_ranges[ax]
            lo = min(lo, arr.min())
            hi = max(hi, arr.max())
            y_ranges[ax] = [lo, hi]
            margin = (hi - lo) * 0.05 if hi > lo else 1.0
            ax.set_ylim(lo - margin, hi + margin)

        return line_mag, line_phase, line_sd

    ani = animation.FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    plt.tight_layout()
    plt.show()
    port.close()


if __name__ == "__main__":
    main()
