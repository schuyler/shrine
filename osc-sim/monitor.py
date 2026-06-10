#!/usr/bin/env python3
"""OSC message logger for debugging."""

import argparse
from datetime import datetime

from pythonosc.dispatcher import Dispatcher
from leds.osc_server import ReusePortOSCUDPServer


def _handler(address, *args):
    now = datetime.now()
    ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
    values = "  ".join(str(a) for a in args)
    print(f"{ts}  {address:<20}  {values}")


def main():
    parser = argparse.ArgumentParser(description="Log incoming OSC messages.")
    parser.add_argument("--host", default="127.0.0.1", help="Listen address")
    parser.add_argument("--port", type=int, default=9001, help="Listen port")
    args = parser.parse_args()

    dispatcher = Dispatcher()
    dispatcher.set_default_handler(_handler)

    server = ReusePortOSCUDPServer((args.host, args.port), dispatcher)
    print(f"Listening for OSC on {args.host}:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
