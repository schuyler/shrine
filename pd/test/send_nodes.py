#!/usr/bin/env python3
"""Send controlled /shrine/node OSC messages to verify osc-receive.

Run the snapshot patch first, then this:
    pd -nogui -noaudio -stderr -path pd pd/test/osctest.pd &
    uv run python pd/test/send_nodes.py

Expected buses (0-1 normalized, clipped):
cap-0=1.0 cap-1=0.5 cap-2=0.25 cap-3=0.75
gsr-mag-0=0.2 gsr-mag-1=0.4 gsr-mag-2=0.6 gsr-mag-3=0.1 gsr-mag-4=0.3 gsr-mag-5=0.5
(carrier_mag slot [1] is dropped; gsr values from NODE_GSR_MAPPING last-writer-wins)
"""
import time
from pythonosc.udp_client import SimpleUDPClient

c = SimpleUDPClient("127.0.0.1", 57120)
msgs = [
    ("/shrine/node/0", [1.0, 0.5, 0.2, 0.4, 0.6]),
    ("/shrine/node/1", [0.5, 0.5, 0.1, 0.3, 0.5]),
    ("/shrine/node/2", [0.25, 0.5, 0.8, 0.24, 0.16]),
    ("/shrine/node/3", [0.75, 0.5, 0.6, 0.12, 0.36]),
]
for _ in range(20):
    for addr, args in msgs:
        c.send_message(addr, args)
    time.sleep(0.05)
