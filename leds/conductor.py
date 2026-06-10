"""Conductor entry point: `python -m leds.conductor`

Wires the OSC sensor stream into the leaky-bucket FSM and fans out cue
messages to the LED stack and Pd.
"""

import argparse
import logging
import random
import threading
import time
from pathlib import Path

import yaml
from pythonosc.dispatcher import Dispatcher
from pythonosc.udp_client import SimpleUDPClient
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from leds.conductor_config import (
    load_conductor_config,
    validate_state_mappings,
    validate_tempo_config,
)
from leds.osc_server import ReusePortOSCUDPServer
from leds.sensor_state import SensorState
from leds.state_machine import GroupChangedEvent, State, StateMachine, StateChangedEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config-driven program/palette mappings (hot-reloadable)
# ---------------------------------------------------------------------------

_mappings_lock = threading.Lock()
_programs: dict[str, str] = {}
_palettes: dict[str, str] = {}


def _get_mappings() -> tuple[dict[str, str], dict[str, str]]:
    with _mappings_lock:
        return _programs, _palettes


def _set_mappings(programs: dict[str, str], palettes: dict[str, str]) -> None:
    # IMPORTANT: Replace module-level references, never mutate dicts in place.
    # This invariant is what makes _get_mappings safe to return references
    # without copying — callers hold a reference to an immutable-in-practice
    # dict that will never be modified, only replaced wholesale.
    global _programs, _palettes
    with _mappings_lock:
        _programs = programs
        _palettes = palettes


class _ConfigReloadHandler(FileSystemEventHandler):
    """Watchdog event handler that hot-reloads programs/palettes from conductor.yaml."""

    def __init__(self, config_path: Path, led_client, current_state_ref):
        super().__init__()
        self._config_path = config_path.resolve()
        self._led_client = led_client
        self._current_state_ref = current_state_ref  # callable returning State
        self._last_reload: float = 0.0

    def on_any_event(self, event):
        # Covers modified, created, and moved (atomic rename).
        # Many editors (vim, neovim, GUI editors) save via atomic rename
        # (write temp + rename), which fires MOVED_TO, not MODIFIED.
        # Filtering on on_any_event with a path check handles all cases.
        src = Path(event.src_path).resolve()
        dest = (
            Path(event.dest_path).resolve()
            if hasattr(event, "dest_path") and event.dest_path
            else None
        )
        if src != self._config_path and dest != self._config_path:
            return
        now = time.monotonic()
        if now - self._last_reload < 0.5:
            return
        self._reload()

    def _reload(self):
        try:
            with open(self._config_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            programs, palettes = validate_state_mappings(raw)
        except Exception:
            logger.warning(
                "Config reload failed; keeping previous mappings",
                exc_info=True,
            )
            return

        _set_mappings(programs, palettes)
        # Update debounce timestamp only on success. If reload fails (bad
        # YAML, missing keys), the next event is NOT suppressed — so a quick
        # correction by the user is picked up immediately.
        self._last_reload = time.monotonic()
        logger.info("Reloaded conductor config mappings")

        # Re-send current state's program/palette to LED stack.
        state = self._current_state_ref()
        name = state.name.lower()
        self._led_client.send_message("/leds/program", programs[name])
        self._led_client.send_message("/leds/palette", palettes[name])

# Major-pentatonic offsets, mirroring pd/mode-table.pd (intervals 0 2 4 7 9).
_PENTATONIC = (0, 2, 4, 7, 9)
# Tonic the conductor picks roots around (C2); matches the shrine-root default.
_ROOT_BASE = 36
# The candidate tonics: one octave of major pentatonic above the base.
_PENTATONIC_ROOTS: tuple[int, ...] = tuple(_ROOT_BASE + i for i in _PENTATONIC)

_RNG = random.Random()


def _pick_pentatonic_root(
    exclude: int | None = None, rng: random.Random = _RNG
) -> int:
    """Pick a major-pentatonic MIDI note for the melodic tonic.

    Avoids immediately repeating ``exclude`` so each quiet feels like a fresh key.
    """
    choices = [r for r in _PENTATONIC_ROOTS if r != exclude] or list(_PENTATONIC_ROOTS)
    return rng.choice(choices)


def _build_shrine_dispatcher(
    sensor_state: SensorState,
    pd_client: SimpleUDPClient | None = None,
) -> Dispatcher:
    dispatcher = Dispatcher()

    def node_handler(address: str, *args):
        # /shrine/node/<id>  →  stdev, carrier_mag, gsr0, gsr1, gsr2
        # Relay the raw sensor stream to Pd so the audio engine and the
        # conductor share one broadcast without Pd needing SO_REUSEPORT.
        if pd_client is not None:
            pd_client.send_message(address, list(args))
        try:
            node_id = int(address.split("/")[-1])
            if 0 <= node_id < 4 and len(args) >= 5:
                sensor_state.update_node(node_id, *[float(a) for a in args[:5]])
            else:
                logger.debug("Out-of-range/short node message: %s %s", address, args)
        except (ValueError, IndexError):
            logger.debug("Malformed node message: %s %s", address, args)

    dispatcher.map("/shrine/node/*", node_handler)

    def default_handler(address, *args):
        logger.debug("Unrecognized OSC: %s", address)
    dispatcher.set_default_handler(default_handler)

    return dispatcher


def main() -> None:
    parser = argparse.ArgumentParser(description="Shrine conductor state machine")
    parser.add_argument("--conductor-config", default=None,
                        help="Path to conductor.yaml override")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=9001,
                        help="OSC port for /shrine/node/* messages")
    parser.add_argument("--led-host", default="127.0.0.1")
    parser.add_argument("--led-port", type=int, default=9000)
    parser.add_argument("--pd-host", default="127.0.0.1")
    parser.add_argument("--pd-port", type=int, default=57120)
    parser.add_argument("--tick-rate", type=float, default=30.0,
                        help="Conductor tick rate in Hz")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level))

    config_path = (
        Path(args.conductor_config).resolve()
        if args.conductor_config
        else (Path(__file__).parent.parent / "conductor.yaml").resolve()
    )

    config = load_conductor_config(config_path)
    sensing_cfg = config["sensing"]
    buckets_cfg = config["buckets"]
    idle_cfg = config["idle"]

    # Validate and install initial mappings (fatal on failure).
    programs_init, palettes_init = validate_state_mappings(config)
    _set_mappings(programs_init, palettes_init)

    sensor_state = SensorState(sensing_cfg)
    fsm = StateMachine(
        buckets_config=buckets_cfg,
        idle_config=idle_cfg,
        confirm_hold=sensing_cfg["confirm_hold"],
    )

    led_client = SimpleUDPClient(args.led_host, args.led_port)
    pd_client = SimpleUDPClient(args.pd_host, args.pd_port)

    # Start watchdog observer for hot-reload of programs/palettes.
    # current_state is captured by name via the lambda closure — each call
    # re-evaluates the name, picking up reassignments in the tick loop.
    # Safe under CPython: State is immutable, GIL makes single ref read/write atomic.
    current_state = State.QUIET
    reload_handler = _ConfigReloadHandler(
        config_path, led_client, lambda: current_state
    )
    observer = Observer()
    observer.schedule(reload_handler, str(config_path.parent), recursive=False)
    observer.daemon = True
    observer.start()

    dispatcher = _build_shrine_dispatcher(sensor_state, pd_client)
    server = ReusePortOSCUDPServer((args.listen_host, args.listen_port), dispatcher)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Tempo config is validated at startup (fatal) but NOT hot-reloaded.
    # Editing the tempo section in conductor.yaml requires a restart.
    tempo_cfg = validate_tempo_config(config)
    last_tempo_send = 0.0

    tick_interval = 1.0 / args.tick_rate
    last = time.monotonic()
    current_root: int | None = None

    logger.info(
        "Conductor running. Listening on %s:%d → LED %s:%d, Pd %s:%d",
        args.listen_host, args.listen_port,
        args.led_host, args.led_port,
        args.pd_host, args.pd_port,
    )

    try:
        while True:
            now = time.monotonic()
            dt = now - last
            last = now

            sensor_state.tick(dt)
            snapshot = sensor_state.snapshot()
            events = fsm.tick(snapshot, dt)

            for event in events:
                if isinstance(event, StateChangedEvent):
                    current_state = event.new
                    name = event.new.name.lower()
                    logger.info("State: %s → %s", event.old.name, event.new.name)
                    programs, palettes = _get_mappings()
                    led_client.send_message("/leds/program", programs[name])
                    led_client.send_message("/leds/palette", palettes[name])
                    pd_client.send_message("/shrine/cue/state", name)
                    if event.new == State.QUIET:
                        # Re-key the piece on each return to stillness: pick a
                        # fresh pentatonic tonic for the melodic voices.
                        current_root = _pick_pentatonic_root(exclude=current_root)
                        logger.info("Quiet → melodic root %d", current_root)
                        pd_client.send_message("/shrine/cue/root", current_root)

                elif isinstance(event, GroupChangedEvent):
                    members = sorted(event.members)
                    logger.debug("Group: %s", members)
                    led_client.send_message("/leds/group", members or [])
                    pd_client.send_message("/shrine/cue/group", members or [])

            # Send tempo at ~1 Hz.
            if now - last_tempo_send >= 1.0:
                bpm = fsm.tempo(tempo_cfg)
                led_client.send_message("/leds/tempo", bpm)
                pd_client.send_message("/shrine/cue/tempo", bpm)
                last_tempo_send = now

            # Relay continuous cap presence to LED stack.
            for pad, val in enumerate(snapshot.raw_cap):
                led_client.send_message("/leds/cap", [pad, val])

            elapsed = time.monotonic() - now
            remaining = tick_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    finally:
        server.shutdown()
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
