"""OSC dispatcher factory for incoming sensor messages."""

import logging
import math

from pythonosc.dispatcher import Dispatcher

from leds.sensor_state import GSR_PAIRS, NODE_GSR_MAPPING, SensorState

logger = logging.getLogger(__name__)

# Map (i,j) tuple to global pair index for fast lookup
_PAIR_TO_INDEX = {pair: idx for idx, pair in enumerate(GSR_PAIRS)}


def build_dispatcher(state: SensorState) -> Dispatcher:
    dispatcher = Dispatcher()

    # /pad/{1..4}/cap handlers
    for pad_num in range(1, 5):
        pad_index = pad_num - 1

        def make_cap_handler(idx):
            def handler(address, value, *args):
                state.set_cap(idx, value)
            return handler

        dispatcher.map(f"/pad/{pad_num}/cap", make_cap_handler(pad_index))

    # /gsr/{i}/{j} magnitude handlers
    for (i, j), global_idx in _PAIR_TO_INDEX.items():
        def make_mag_handler(gidx):
            def handler(address, value, *args):
                state.set_gsr_mag(gidx, value)
            return handler

        dispatcher.map(f"/gsr/{i}/{j}", make_mag_handler(global_idx))

    # /gsr/{i}/{j}/phase handlers (simulator: store as-is, no normalization)
    for (i, j), global_idx in _PAIR_TO_INDEX.items():
        def make_phase_handler(gidx):
            def handler(address, value, *args):
                state.set_gsr_phase(gidx, value)
            return handler

        dispatcher.map(f"/gsr/{i}/{j}/phase", make_phase_handler(global_idx))

    # /shrine/node/{0..3} edge node handlers
    for node_id in range(4):
        def make_node_handler(nid):
            def handler(address, cap, m0, m1, m2, p0, p1, p2, *args):
                state.set_cap(nid, cap)
                local_mags = [m0, m1, m2]
                local_phases = [p0, p1, p2]
                for local_idx, global_idx in enumerate(NODE_GSR_MAPPING[nid]):
                    phase = local_phases[local_idx]
                    if phase < 0:
                        phase += 2 * math.pi
                    state.set_gsr(global_idx, local_mags[local_idx], phase)
            return handler

        dispatcher.map(f"/shrine/node/{node_id}", make_node_handler(node_id))

    # Default handler for unrecognized addresses
    def default_handler(address, *args):
        logger.debug("Unrecognized OSC address: %s", address)

    dispatcher.set_default_handler(default_handler)

    return dispatcher
