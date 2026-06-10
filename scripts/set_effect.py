#!/usr/bin/env python3
"""Force a WLED effect onto a pad via the LED controller's OSC surface.

A small convenience wrapper around the ``/leds/effect`` control so you can
test the lighting independently of the conductor / state program.  The LED
controller (`python -m leds`) must be running; this just sends it OSC.

Examples
--------
    # drive pad 0 to the "rainbow" effect
    python scripts/set_effect.py 0 rainbow

    # a numeric WLED fx ID works too, with brightness/speed/intensity
    python scripts/set_effect.py 1 28 --bri 200 --sx 180 --ix 100

    # release the override on a pad
    python scripts/set_effect.py 0 off

    # release every override
    python scripts/set_effect.py --clear-all

    # list the known effect names
    python scripts/set_effect.py --list
"""
import argparse
import os
import sys

# Make `import leds` work whether run as `python scripts/set_effect.py` or
# `python -m scripts.set_effect`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pythonosc.udp_client import SimpleUDPClient  # noqa: E402

from leds.effects import EffectIndex, fetch_effect_names  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pad", nargs="?", type=int, help="0-indexed pad ID")
    parser.add_argument("effect", nargs="?",
                        help="effect name, numeric WLED fx ID, or off/clear")
    parser.add_argument("--bri", type=int, default=255, help="brightness 0-255")
    parser.add_argument("--sx", type=int, default=128, help="effect speed 0-255")
    parser.add_argument("--ix", type=int, default=128, help="effect intensity 0-255")
    parser.add_argument("--pal", type=int, default=0, help="WLED palette index")
    parser.add_argument("--host", default="127.0.0.1", help="LED controller host")
    parser.add_argument("--port", type=int, default=9000, help="LED controller OSC port")
    parser.add_argument("--wled-host", default=None,
                        help="fetch live effect names from this WLED node "
                             "(otherwise uses the built-in name table)")
    parser.add_argument("--wled-port", type=int, default=80, help="WLED HTTP port")
    parser.add_argument("--list", action="store_true", help="list known effect names and exit")
    parser.add_argument("--clear-all", action="store_true",
                        help="release every manual effect override")
    args = parser.parse_args()

    # Resolve names against the live node list if one was given, else the
    # built-in table.  This matches whatever the LED controller itself uses.
    effects = EffectIndex()
    if args.wled_host:
        names = fetch_effect_names(args.wled_host, args.wled_port)
        if names:
            effects.update_from_names(names)
        else:
            print(f"Warning: could not fetch effects from {args.wled_host}; "
                  "using built-in names", file=sys.stderr)

    if args.list:
        print("\n".join(effects.names()))
        return

    client = SimpleUDPClient(args.host, args.port)

    if args.clear_all:
        client.send_message("/leds/effect/clear", [])
        print(f"Cleared all effect overrides → {args.host}:{args.port}")
        return

    if args.pad is None or args.effect is None:
        parser.error("pad and effect are required (or use --list / --clear-all)")

    clear_tokens = {"off", "clear", "none"}
    if args.effect.strip().lower() in clear_tokens:
        client.send_message("/leds/effect", [args.pad, args.effect])
        print(f"Cleared effect on pad {args.pad} → {args.host}:{args.port}")
        return

    if effects.resolve(args.effect) is None:
        parser.error(
            f"unknown effect {args.effect!r}; use a numeric fx ID or one of "
            f"--list names"
        )

    client.send_message(
        "/leds/effect",
        [args.pad, args.effect, args.bri, args.sx, args.ix, args.pal],
    )
    print(f"Set pad {args.pad} → effect {args.effect} "
          f"(bri={args.bri} sx={args.sx} ix={args.ix} pal={args.pal}) "
          f"→ {args.host}:{args.port}")


if __name__ == "__main__":
    sys.exit(main())
