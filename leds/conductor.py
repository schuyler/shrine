"""Conductor entry point: `python -m leds.conductor`

Wires the OSC sensor stream into the leaky-bucket FSM and fans out cue
messages to the LED stack and Pd.
"""

import argparse
import logging
import threading
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.udp_client import SimpleUDPClient

from leds.conductor_config import load_conductor_config
from leds.osc_server import ReusePortOSCUDPServer
from leds.sensor_state import SensorState
from leds.state_machine import GroupChangedEvent, State, StateMachine, StateChangedEvent

logger = logging.getLogger(__name__)

# Program and palette names to send to the LED stack on each state transition.
# Values here are placeholders to reconcile with Lighting_Architecture.
_STATE_PROGRAMS: dict[State, str] = {
    State.QUIET: "breathe",
    State.SEEKING: "chase",
    State.ALIGNING: "breathe",
    State.ENERGIZING: "breathe",
    State.ASCENDING: "breathe",
}
_STATE_PALETTES: dict[State, str] = {
    State.QUIET: "default",
    State.SEEKING: "default",
    State.ALIGNING: "default",
    State.ENERGIZING: "default",
    State.ASCENDING: "default",
}


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
            if len(args) >= 5:
                sensor_state.update_node(node_id, *[float(a) for a in args[:5]])
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

    config = load_conductor_config(args.conductor_config)
    sensing_cfg = config["sensing"]
    buckets_cfg = config["buckets"]
    idle_cfg = config["idle"]

    sensor_state = SensorState(sensing_cfg)
    fsm = StateMachine(
        buckets_config=buckets_cfg,
        idle_config=idle_cfg,
        confirm_hold=sensing_cfg["confirm_hold"],
    )

    led_client = SimpleUDPClient(args.led_host, args.led_port)
    pd_client = SimpleUDPClient(args.pd_host, args.pd_port)

    dispatcher = _build_shrine_dispatcher(sensor_state, pd_client)
    server = ReusePortOSCUDPServer((args.listen_host, args.listen_port), dispatcher)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    tick_interval = 1.0 / args.tick_rate
    last = time.monotonic()
    current_state = State.QUIET

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
                    led_client.send_message("/leds/program", _STATE_PROGRAMS[event.new])
                    led_client.send_message("/leds/palette", _STATE_PALETTES[event.new])
                    pd_client.send_message("/shrine/cue/state", name)

                elif isinstance(event, GroupChangedEvent):
                    members = sorted(event.members)
                    logger.debug("Group: %s", members)
                    led_client.send_message("/leds/group", members or [])
                    pd_client.send_message("/shrine/cue/group", members or [])

            # Relay continuous cap presence to LED stack.
            for pad, val in enumerate(snapshot.raw_cap):
                led_client.send_message("/leds/cap", [pad, val])

            elapsed = time.monotonic() - now
            remaining = tick_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
