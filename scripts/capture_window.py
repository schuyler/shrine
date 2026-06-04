#!/usr/bin/env python3
"""
Capture a raw ADC window dump from fdm-bench firmware.

Sends the 'd' command over serial, reads 1800 sample lines + END marker,
and writes the samples to a file (one integer per line).

Usage:
    python scripts/capture_window.py /dev/ttyUSB0 baseline.txt
    python scripts/capture_window.py /dev/ttyUSB0 bridged.txt
"""

import sys
import serial

BAUD = 115200
WINDOW_SIZE = 1800


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <serial-port> <output-file>", file=sys.stderr)
        sys.exit(1)

    port_path = sys.argv[1]
    output_path = sys.argv[2]

    port = serial.Serial(port_path, BAUD, timeout=10)

    # Drain any buffered output before sending the dump command
    port.reset_input_buffer()
    port.write(b"d")
    port.flush()

    samples = []
    while True:
        line = port.readline().decode("ascii", errors="replace").strip()
        if not line:
            continue
        if line == "END":
            break
        try:
            samples.append(int(line))
        except ValueError:
            # Skip non-integer lines (e.g. log messages during dump)
            continue

    port.close()

    if len(samples) != WINDOW_SIZE:
        print(
            f"Warning: expected {WINDOW_SIZE} samples, got {len(samples)}",
            file=sys.stderr,
        )

    with open(output_path, "w") as f:
        for s in samples:
            f.write(f"{s}\n")

    print(f"{len(samples)} samples written to {output_path}")


if __name__ == "__main__":
    main()
