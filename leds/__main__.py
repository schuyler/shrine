"""Entry point for `python -m leds`."""
import argparse
import logging
import threading
import time

from leds.clock import Clock
from leds.config import load_config
from leds.osc_input import build_dispatcher
from leds.osc_server import ReusePortOSCUDPServer
from leds.pad_state import PadState
from leds.palettes import load_palettes
from leds.programs import get_program
from leds.wled import WledDispatcher

logger = logging.getLogger(__name__)

_EMA_ALPHA = 0.1  # smoothing for RTT EMA


def main():
    parser = argparse.ArgumentParser(description="Shrine LED controller")
    parser.add_argument("--config", default=None, help="Path to custom config YAML")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    config = load_config(args.config)
    pads_config = config["pads"]

    state = PadState(pads_config)
    state.set_program(config["default_program"])
    state.set_palette(config["default_palette"])

    sig_colors = {t["pad"]: t["color"] for t in config["wled_targets"] if t.get("color") is not None}
    if sig_colors:
        state.set_signature_colors(sig_colors)

    dispatcher = build_dispatcher(state)
    wled = WledDispatcher(
        targets=config["wled_targets"],
        port=config["wled_port"],
        timeout=config["wled_timeout"],
    )

    palettes = load_palettes()

    latency_cfg = config["latency_offset_ms"]
    initial_offset = 0.0 if latency_cfg == "auto" else float(latency_cfg)
    clock = Clock(latency_offset_ms=initial_offset)
    auto_latency = latency_cfg == "auto"
    rtt_ema = None

    program = get_program(config["default_program"])
    program_state = program.initial_state()
    current_program_name = config["default_program"]
    current_palette_name = config["default_palette"]
    palette = palettes.get(current_palette_name, palettes.get("default"))

    server = ReusePortOSCUDPServer(
        (config["osc_listen_host"], config["osc_listen_port"]), dispatcher)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    update_interval = 1.0 / config["update_rate_hz"]
    last_tempo_gen = 0
    logger.info("Shrine LED controller running. OSC on %s:%s",
                config["osc_listen_host"], config["osc_listen_port"])

    try:
        while True:
            t0 = time.monotonic()

            pad_snaps, snap_program, snap_palette, bpm, sync_time, tempo_gen = state.snapshot()

            # Handle program switch
            if snap_program and snap_program != current_program_name:
                try:
                    program = get_program(snap_program)
                    program_state = program.initial_state()
                    current_program_name = snap_program
                    logger.info("Program switched to: %s", current_program_name)
                except KeyError:
                    logger.warning("Unknown program: %s", snap_program)
                    current_program_name = snap_program

            # Handle palette switch
            if snap_palette and snap_palette != current_palette_name:
                new_palette = palettes.get(snap_palette)
                if new_palette is not None:
                    palette = new_palette
                    current_palette_name = snap_palette
                    logger.info("Palette switched to: %s", current_palette_name)
                else:
                    logger.warning("Unknown palette: %s", snap_palette)
                    current_palette_name = snap_palette

            # Handle tempo sync
            if tempo_gen != last_tempo_gen:
                clock.sync(bpm, sync_time)
                last_tempo_gen = tempo_gen

            phase = clock.phase(t0)
            segments, program_state = program.render(pad_snaps, palette, phase, program_state)

            pad_segments = dict(zip(pads_config, segments))
            rtt = wled.send(pad_segments)

            if auto_latency and rtt is not None:
                if rtt_ema is None:
                    rtt_ema = rtt
                else:
                    rtt_ema = _EMA_ALPHA * rtt + (1 - _EMA_ALPHA) * rtt_ema
                clock.latency_offset_ms = rtt_ema / 2

            elapsed = time.monotonic() - t0
            remaining = update_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
    finally:
        server.shutdown()
        wled.close()


if __name__ == "__main__":
    main()
