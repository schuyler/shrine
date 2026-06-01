#!/usr/bin/env python3
"""
Offline analysis tools for fdm-bench serial-captured sample data.

Functions:
    load_samples(filename)       -- load serial-dumped samples (one int per line)
    bin_magnitude(samples, k, N) -- I/Q magnitude via incremental rotation
    spectral_plot(filename, fs, carriers, N=1800) -- FFT with carrier bins marked
    shunt_compare(baseline_file, shunted_file, k, N=1800) -- magnitude comparison in dB

Usage:
    python fdm_analysis.py spectrum <filename> <fs> [--carriers 180 200 220 240]
    python fdm_analysis.py shunt <baseline> <shunted> <k> [--N 1800]

Requires: numpy, matplotlib
"""

import argparse
import numpy as np
import matplotlib.pyplot as plt


def load_samples(filename):
    """Load serial-dumped samples from a file.

    The file is expected to contain one integer per line, as produced by
    the firmware's 'd' (dump) command.  A trailing 'END' line is ignored.

    Returns a numpy array of uint16 (12-bit ADC values, range 0–4095).
    """
    samples = []
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if not line or line == "END":
                continue
            samples.append(int(line))
    return np.array(samples, dtype=np.uint16)


def bin_magnitude(samples, k, N):
    """Compute the DFT magnitude at bin k using incremental NCO rotation.

    Mirrors the firmware's process_window() algorithm exactly, including
    DC removal and periodic renormalization every 64 steps.

    Sign convention note: the firmware uses negative rotation
    (standard DFT: e^{-j*2*pi*k*n/N}) by negating sin_step.  The loop
    below uses the wiki's positive-rotation form:
        rc, rs = rc*cs - rs*sn, rs*cs + rc*sn
    Magnitude is invariant to conjugation (sqrt(I^2+Q^2) is the same for
    both signs), so the numerical result is identical.

    Returns magnitude normalized by N (matches firmware output units).
    """
    if len(samples) < N:
        raise ValueError(f"Need at least {N} samples, got {len(samples)}")
    samples = samples[:N]

    mean = np.mean(samples.astype(np.float64))

    theta = 2.0 * np.pi * k / N
    cs = np.cos(theta)
    sn = np.sin(theta)

    NCO_RENORM_INTERVAL = 64
    rc, rs = 1.0, 0.0
    I, Q = 0.0, 0.0
    renorm_counter = 0

    for n in range(N):
        s = float(samples[n]) - mean  # DC removal
        I += s * rc
        Q += s * rs

        # Rotate NCO phasor by one step (positive rotation; see sign note above)
        rc, rs = rc * cs - rs * sn, rs * cs + rc * sn

        renorm_counter += 1
        if renorm_counter >= NCO_RENORM_INTERVAL:
            mag = np.sqrt(rc * rc + rs * rs)
            rc /= mag
            rs /= mag
            renorm_counter = 0

    return np.sqrt(I * I + Q * Q) / N


def spectral_plot(filename, fs, carriers, N=1800):
    """Plot the FFT spectrum of a sample file with carrier bins marked.

    Parameters
    ----------
    filename : str
        Path to a serial-dumped sample file (one int per line).
    fs : float
        Measured sample rate in Hz (from firmware's fs_measured log line).
    carriers : list of int
        Bin indices to mark (e.g. [180, 200, 220, 240]).
    N : int
        Window size (default 1800, must match firmware WINDOW_SIZE).
    """
    samples = load_samples(filename)
    if len(samples) < N:
        raise ValueError(f"Need at least {N} samples, got {len(samples)}")

    window = samples[:N].astype(np.float64)
    dc = np.mean(window)
    spectrum = np.abs(np.fft.rfft(window - dc)) / N
    freqs = np.fft.rfftfreq(N, d=1.0 / fs)
    bins = np.arange(len(spectrum))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # Full spectrum in dB
    ax1.plot(freqs / 1000, 20 * np.log10(spectrum + 1e-12))
    for k in carriers:
        ax1.axvline(k * fs / N / 1000, color='r', alpha=0.5, ls='--')
    ax1.set_xlabel('Frequency (kHz)')
    ax1.set_ylabel('Magnitude (dB)')
    ax1.set_title('Full spectrum')

    # Zoom on carrier region — stem plot in bins
    k_min = min(carriers) - 5
    k_max = max(carriers) + 5
    mask = (bins >= k_min) & (bins <= k_max)
    ax2.stem(bins[mask], 20 * np.log10(spectrum[mask] + 1e-12))
    for k in carriers:
        ax2.axvline(k, color='r', alpha=0.5, ls='--')
    ax2.set_xlabel('DFT bin')
    ax2.set_ylabel('Magnitude (dB)')
    ax2.set_title('Carrier region (bin detail)')

    plt.tight_layout()
    plt.savefig(filename.replace('.txt', '_spectrum.png'), dpi=150)
    plt.show()


def shunt_compare(baseline_file, shunted_file, k, N=1800):
    """Compare bin magnitude between baseline and shunted captures in dB.

    Loads one window of N samples from each file, computes bin_magnitude()
    for bin k, and prints/plots the difference in dB.

    Parameters
    ----------
    baseline_file : str
        Path to baseline serial-dump file.
    shunted_file : str
        Path to shunted serial-dump file.
    k : int
        Bin index to compare.
    N : int
        Window size (default 1800).
    """
    baseline = load_samples(baseline_file)
    shunted = load_samples(shunted_file)

    mag_base = bin_magnitude(baseline, k, N)
    mag_shunt = bin_magnitude(shunted, k, N)

    if mag_base == 0:
        raise ValueError("Baseline magnitude is zero — cannot compute dB ratio")

    db = 20.0 * np.log10(mag_shunt / mag_base)

    print(f"Bin k={k}")
    print(f"  Baseline magnitude : {mag_base:.4f}")
    print(f"  Shunted magnitude  : {mag_shunt:.4f}")
    print(f"  Delta              : {db:+.2f} dB")

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(["Baseline", "Shunted"], [mag_base, mag_shunt], color=["steelblue", "tomato"])
    ax.set_ylabel("Magnitude (normalized)")
    ax.set_title(f"Shunt comparison — bin k={k}  ({db:+.2f} dB)")
    ax.bar_label(bars, fmt="%.4f", padding=3)
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.show()

    return db


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Offline analysis for fdm-bench serial captures."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # spectrum subcommand
    sp_spectrum = subparsers.add_parser(
        "spectrum",
        help="Plot FFT spectrum with carrier bins marked."
    )
    sp_spectrum.add_argument("filename", help="Serial-dump file (one int per line)")
    sp_spectrum.add_argument("fs", type=float, help="Measured sample rate in Hz")
    sp_spectrum.add_argument(
        "--carriers", type=int, nargs="+", default=[180, 200, 220, 240],
        metavar="K",
        help="Bin indices to mark (default: 180 200 220 240)"
    )
    sp_spectrum.add_argument("--N", type=int, default=1800,
                             help="Window size (default 1800)")

    # shunt subcommand
    sp_shunt = subparsers.add_parser(
        "shunt",
        help="Compare baseline vs. shunted magnitude at bin k."
    )
    sp_shunt.add_argument("baseline", help="Baseline serial-dump file")
    sp_shunt.add_argument("shunted", help="Shunted serial-dump file")
    sp_shunt.add_argument("k", type=int, help="Bin index to compare")
    sp_shunt.add_argument("--N", type=int, default=1800,
                          help="Window size (default 1800)")

    args = parser.parse_args()

    if args.command == "spectrum":
        spectral_plot(args.filename, args.fs, args.carriers, N=args.N)
    elif args.command == "shunt":
        shunt_compare(args.baseline, args.shunted, args.k, N=args.N)
