"""OSC dispatcher factory for incoming sensor messages."""

import logging
import time

from pythonosc.dispatcher import Dispatcher

from leds.pad_state import PadState

logger = logging.getLogger(__name__)


def build_dispatcher(state: PadState) -> Dispatcher:
    dispatcher = Dispatcher()

    # /leds/cap <pad_0idx> <float 0-1>
    def cap_handler(address, pad, value, *args):
        state.set_cap(int(pad), float(value))
    dispatcher.map("/leds/cap", cap_handler)

    # /leds/heartbeat <pad_0idx> <float Hz>
    def heartbeat_handler(address, pad, value, *args):
        state.set_heartbeat(int(pad), float(value))
    dispatcher.map("/leds/heartbeat", heartbeat_handler)

    # /leds/flux <pad_0idx> <float 0-1>
    def flux_handler(address, pad, value, *args):
        state.set_flux(int(pad), float(value))
    dispatcher.map("/leds/flux", flux_handler)

    # /leds/program <name>
    def program_handler(address, name, *args):
        state.set_program(str(name))
    dispatcher.map("/leds/program", program_handler)

    # /leds/palette <name>
    def palette_handler(address, name, *args):
        state.set_palette(str(name))
    dispatcher.map("/leds/palette", palette_handler)

    # /leds/tempo <bpm>
    def tempo_handler(address, bpm, *args):
        state.set_tempo(float(bpm), time.monotonic())
    dispatcher.map("/leds/tempo", tempo_handler)

    def default_handler(address, *args):
        logger.debug("Unrecognized OSC address: %s", address)
    dispatcher.set_default_handler(default_handler)

    return dispatcher
