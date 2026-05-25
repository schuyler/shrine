"""Entry point for `python -m leds`."""

import argparse
import logging
import socket
import threading
import time

from pythonosc.server import ThreadingOSCUDPServer

from leds.config import load_config
from leds.mapping import MappingEngine
from leds.osc_input import build_dispatcher
from leds.sensor_state import SensorState
from leds.wled import WledClient

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Shrine LED controller")
    parser.add_argument("--config", default=None, help="Path to custom config YAML")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level))

    config = load_config(args.config)
    state = SensorState()
    dispatcher = build_dispatcher(state)
    engine = MappingEngine(config)
    client = WledClient(
        host=config["wled_host"],
        port=config["wled_port"],
        timeout=config["wled_timeout"],
    )

    listen_host = config["osc_listen_host"]
    listen_port = config["osc_listen_port"]

    server = ThreadingOSCUDPServer((listen_host, listen_port), dispatcher)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    update_interval = 1.0 / config["update_rate_hz"]
    logger.info("Shrine LED controller running. OSC on %s:%s", listen_host, listen_port)

    try:
        while True:
            t0 = time.monotonic()
            snapshot = state.snapshot()
            segments = engine.compute(*snapshot)
            client.send(segments)
            elapsed = time.monotonic() - t0
            remaining = update_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
