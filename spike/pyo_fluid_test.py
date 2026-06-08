"""
Spike: validate pyo + pyfluidsynth for art installation sound engine.

Usage:
    python spike/pyo_fluid_test.py <soundfont.sf2> [--device INT] [--duration SECS]
"""

import argparse
import sys
import threading
import time
from datetime import datetime


def ts():
    """Return current timestamp string [HH:MM:SS.mmm]."""
    now = datetime.now()
    return f"[{now.strftime('%H:%M:%S')}.{now.microsecond // 1000:03d}]"


def log(msg):
    print(f"{ts()} {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="pyo + pyfluidsynth spike test")
    parser.add_argument("soundfont", help="Path to .sf2 soundfont file")
    parser.add_argument("--device", type=int, default=None, help="Output audio device index")
    parser.add_argument("--duration", type=float, default=10.0, help="Test duration in seconds (default: 10)")
    args = parser.parse_args()

    # --- pyo import and device listing ---
    try:
        import pyo
    except ImportError as e:
        log(f"ERROR: failed to import pyo: {e}")
        sys.exit(1)

    log("Available audio devices:")
    pyo.pa_list_devices()

    # --- pyo server setup ---
    SR = 48000
    BUFSIZE = 256

    try:
        server = pyo.Server(nchnls=8, sr=SR, buffersize=BUFSIZE)
        if args.device is not None:
            log(f"Setting output device to index {args.device}")
            server.setOutputDevice(args.device)
        server.boot()
        server.start()
        log("pyo server booted and started (sr=48000, buffersize=256, nchnls=8)")
    except Exception as e:
        log(f"ERROR: pyo server failed to boot: {e}")
        sys.exit(1)

    # --- fluidsynth setup ---
    try:
        import fluidsynth
    except ImportError as e:
        log(f"ERROR: failed to import fluidsynth: {e}")
        server.stop()
        server.shutdown()
        sys.exit(1)

    try:
        fs = fluidsynth.Synth(samplerate=48000)
    except Exception as e:
        log(f"ERROR: failed to create fluidsynth.Synth: {e}")
        server.stop()
        server.shutdown()
        sys.exit(1)

    try:
        sfid = fs.sfload(args.soundfont)
        if sfid == -1:
            raise RuntimeError("sfload returned -1 — file not found or invalid")
        fs.program_select(0, sfid, 0, 0)
        log(f"Soundfont loaded: {args.soundfont} (sfid={sfid}, channel=0, bank=0, preset=0)")
    except Exception as e:
        log(f"ERROR: failed to load soundfont: {e}")
        fs.delete()
        server.stop()
        server.shutdown()
        sys.exit(1)

    # --- channel 0: additive drone ---
    log("Setting up additive drone on output channel 0")
    amp_ramp = pyo.SigTo(value=0, time=2)

    osc_fundamental = pyo.Sine(freq=130.81, mul=0.5)
    osc_octave      = pyo.Sine(freq=261.62, mul=0.25)
    osc_celeste     = pyo.Sine(freq=132.31, mul=0.3)

    drone_mix = (osc_fundamental + osc_octave + osc_celeste) * amp_ramp
    drone_out = drone_mix.out(chnl=0)

    amp_ramp.setValue(1.0)
    log("Drone ramping to amplitude 1.0 over 2 seconds (C3 fundamental + octave + celeste detune)")

    # --- channel 1: fluidsynth via double-buffer table ---
    log("Setting up fluidsynth playback on output channel 1")

    table_length_sec = BUFSIZE / SR  # e.g. 256/48000 ≈ 0.00533 s
    fluid_table = pyo.NewTable(length=table_length_sec)

    import numpy as np

    def fluid_callback():
        """Called each audio cycle. Pull samples from fluidsynth into pyo table."""
        try:
            # get_samples returns interleaved stereo int16, length = buffersize * 2
            raw = fs.get_samples(BUFSIZE)
            mono = (raw[::2].astype(np.float32) / 32768.0).tolist()  # left ch, normalize
            fluid_table.copyDataFromList(mono)
        except Exception:
            pass  # spike: swallow errors silently in callback

    server.setCallback(fluid_callback)

    table_reader = pyo.TableRead(fluid_table, freq=SR / BUFSIZE, loop=True)
    table_reader.out(chnl=1)
    log(f"TableRead playing fluid_table at freq={SR/BUFSIZE:.2f} Hz (= sr/buffersize), loop=True -> chnl=1")

    # --- note sequence ---
    NOTES = [60, 62, 64, 65, 67, 69, 71, 72]  # C4 through C5
    NOTE_NAMES = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
    note_state = {"index": 0, "active": None, "timer": None, "running": True}

    def play_next_note():
        if not note_state["running"]:
            return
        prev = note_state["active"]
        if prev is not None:
            fs.noteoff(0, prev)
        idx = note_state["index"]
        if idx < len(NOTES):
            note = NOTES[idx]
            fs.noteon(0, note, 100)
            log(f"FluidSynth note: {NOTE_NAMES[idx]} (midi={note}) on channel 1")
            note_state["active"] = note
            note_state["index"] = idx + 1
            if note_state["running"]:
                t = threading.Timer(1.0, play_next_note)
                t.daemon = True
                note_state["timer"] = t
                t.start()
        else:
            log("FluidSynth note sequence complete")
            note_state["active"] = None

    log("Starting note sequence: C4 D4 E4 F4 G4 A4 B4 C5, one per second")
    play_next_note()

    # --- run for duration ---
    log(f"Running for {args.duration:.1f} seconds...")
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        log("Interrupted by user")

    # --- clean shutdown ---
    log("Shutting down...")
    note_state["running"] = False
    if note_state["timer"] is not None:
        note_state["timer"].cancel()
    if note_state["active"] is not None:
        fs.noteoff(0, note_state["active"])

    server.stop()
    log("pyo server stopped")

    fs.delete()
    log("FluidSynth deleted")

    server.shutdown()
    log("pyo server shut down")


if __name__ == "__main__":
    main()
