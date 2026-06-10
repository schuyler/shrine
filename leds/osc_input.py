"""OSC dispatcher factory for incoming sensor messages."""

import logging
import time

from pythonosc.dispatcher import Dispatcher

from leds.effects import EffectIndex
from leds.pad_state import EffectOverride, PadState

logger = logging.getLogger(__name__)


def build_dispatcher(state: PadState, effects: EffectIndex | None = None) -> Dispatcher:
    if effects is None:
        effects = EffectIndex()
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

    # /leds/effect <pad> <name|fx_id> [bri] [sx] [ix] [pal]
    # Forces a named WLED effect onto a pad, overriding the running program
    # until cleared.  Lets you test lighting without the conductor.  Use a
    # name like "rainbow", a numeric WLED fx ID, or "off"/"clear" to release.
    _CLEAR_TOKENS = {"off", "clear", "none"}

    def effect_handler(address, pad, effect, *args):
        pad = int(pad)
        if str(effect).strip().lower() in _CLEAR_TOKENS:
            state.clear_effect(pad)
            return
        fx = effects.resolve(effect)
        if fx is None:
            logger.warning("Unknown WLED effect: %r", effect)
            return
        bri = int(args[0]) if len(args) > 0 else 255
        sx = int(args[1]) if len(args) > 1 else 128
        ix = int(args[2]) if len(args) > 2 else 128
        pal = int(args[3]) if len(args) > 3 else 0
        state.set_effect(pad, EffectOverride(fx=fx, bri=bri, sx=sx, ix=ix, pal=pal))
    dispatcher.map("/leds/effect", effect_handler)

    # /leds/effect/clear   — release all manual effect overrides at once
    def effect_clear_handler(address, *args):
        state.clear_all_effects()
    dispatcher.map("/leds/effect/clear", effect_clear_handler)

    # /leds/group <pad0> <pad1> ... (variable number of 0-indexed pad IDs)
    def group_handler(address, *args):
        state.set_group(frozenset(int(p) for p in args))
    dispatcher.map("/leds/group", group_handler)

    def default_handler(address, *args):
        logger.debug("Unrecognized OSC address: %s", address)
    dispatcher.set_default_handler(default_handler)

    return dispatcher
