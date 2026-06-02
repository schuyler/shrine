"""OSC dispatcher factory for incoming sensor messages."""

import logging

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

    # /shrine/node/{0..3} edge node handlers
    # FDM format: stdev, carrier_mag, m0, m1, m2
    # stdev is used as cap; carrier_mag is ignored; all 3 GSR slots are always populated.
    for node_id in range(4):
        def make_node_handler(nid):
            def handler(address, stdev, carrier_mag, m0, m1, m2, *args):
                state.set_cap(nid, stdev)
                local_mags = [m0, m1, m2]
                for local_idx, global_idx in enumerate(NODE_GSR_MAPPING[nid]):
                    state.set_gsr_mag(global_idx, local_mags[local_idx])
            return handler

        dispatcher.map(f"/shrine/node/{node_id}", make_node_handler(node_id))

    # Default handler for unrecognized addresses
    def default_handler(address, *args):
        logger.debug("Unrecognized OSC address: %s", address)

    dispatcher.set_default_handler(default_handler)

    return dispatcher
