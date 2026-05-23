#!/usr/bin/env python3
"""Read GSR sensor data from serial and output a sine wave tone."""

import array
import math
import sys

import numpy as np
import serial
import sounddevice as sd

# Serial
SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200

# Audio
AUDIO_DEVICE = None  # None = system default; set to int device index if needed
SAMPLE_RATE = 44100

# Mapping: filtered millivolts -> frequency
MV_MIN = 1500.0
MV_MAX = 3150.0
FREQ_MIN = 200.0
FREQ_MAX = 800.0

# Shared state: one-element float arrays for lock-free access from audio thread
_target_freq = array.array("f", [FREQ_MIN])
_current_freq = array.array("f", [FREQ_MIN])
_phase = array.array("f", [0.0])

# Smoothing: per-sample interpolation toward target frequency
# At 44100 Hz, 0.001 gives ~10ms glide time
FREQ_SMOOTHING = 0.001


def _audio_callback(outdata, frames, _time, _status):
    target = _target_freq[0]
    freq = _current_freq[0]
    phase = _phase[0]

    # Build per-sample frequency array via exponential smoothing
    alpha = FREQ_SMOOTHING
    # After n samples: freq_n = target + (freq_0 - target) * (1 - alpha)^n
    decay = (1.0 - alpha) ** np.arange(frames, dtype=np.float64)
    freqs = target + (freq - target) * decay

    # Accumulate phase from per-sample frequencies
    phase_increments = 2.0 * np.pi * freqs / SAMPLE_RATE
    phases = phase + np.cumsum(phase_increments)

    outdata[:, 0] = np.sin(phases).astype(np.float32)

    _current_freq[0] = freqs[-1]
    _phase[0] = phases[-1] % (2.0 * np.pi)


def _mv_to_freq(mv: float) -> float:
    clamped = max(MV_MIN, min(MV_MAX, mv))
    ratio = (clamped - MV_MIN) / (MV_MAX - MV_MIN)
    return FREQ_MIN + ratio * (FREQ_MAX - FREQ_MIN)


def main():
    print(f"Opening {SERIAL_PORT} at {BAUD_RATE} baud")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

    stream = sd.OutputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=AUDIO_DEVICE,
        callback=_audio_callback,
    )
    stream.start()
    print(f"Streaming tone to audio device (freq {FREQ_MIN}-{FREQ_MAX} Hz)")

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="replace").strip()
            if not line or line.startswith("raw_adc"):
                continue
            try:
                fields = line.split("\t")
                filtered_mv = float(fields[4])
            except (ValueError, IndexError):
                continue
            freq = _mv_to_freq(filtered_mv)
            _target_freq[0] = freq
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        stream.close()
        ser.close()


if __name__ == "__main__":
    main()
