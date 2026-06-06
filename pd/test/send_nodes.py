#!/usr/bin/env python3
"""Send controlled /shrine/node OSC messages to verify osc-receive.

Run the snapshot patch first, then this:
    pd -nogui -noaudio -stderr -path pd pd/test/osctest.pd &
    uv run python pd/test/send_nodes.py

Expected buses: cap-1=1 cap-2=0.5 cap-3=0.25 cap-4=0.75 ;
gsr-mag-0=0.5 gsr-mag-1=0.24 gsr-mag-2=0.8 gsr-mag-3=0.16 gsr-mag-4=0.12 gsr-mag-5=0.36
"""
import time
from pythonosc.udp_client import SimpleUDPClient

c = SimpleUDPClient("127.0.0.1", 57120)
msgs = [
    ("/shrine/node/0", [1000.0, 200.0, 10.0, 20.0, 30.0]),
    ("/shrine/node/1", [500.0, 200.0, 5.0, 15.0, 25.0]),
    ("/shrine/node/2", [250.0, 200.0, 50.0, 12.0, 8.0]),
    ("/shrine/node/3", [750.0, 200.0, 40.0, 6.0, 18.0]),
]
for _ in range(20):
    for addr, args in msgs:
        c.send_message(addr, args)
    time.sleep(0.05)
