"""OSC UDP server that permits port sharing across processes.

Mirrors corazon's ``ReusePortBlockingOSCUDPServer``: a single-reader-thread
blocking server that sets ``SO_REUSEPORT`` *before* bind, so several processes
can bind the same UDP port and each receive a copy of every **broadcast**
datagram. (For unicast, ``SO_REUSEPORT`` load-balances and only one socket gets
each packet; broadcast/multicast is delivered to all of them — which is exactly
why the shrine sensor nodes broadcast.)

``SO_BROADCAST`` is also set, matching corazon. It is strictly a send-side flag
on Linux (receiving broadcast works without it), so this is belt-and-suspenders.

``SO_REUSEPORT`` is Linux / newer-BSD only; on platforms without it the option
is skipped and the server still binds — but only a single consumer can share
the port there. Every socket sharing a port must set ``SO_REUSEPORT``, so Pd
(whose ``[osc.receive]`` does not) cannot join the shared bind; feed it by
forwarding instead.

Unlike ``ThreadingOSCUDPServer`` (a thread per datagram), the blocking server
drains the socket from one reader thread — no per-message thread churn.
"""

import socket

from pythonosc.osc_server import BlockingOSCUDPServer


class ReusePortOSCUDPServer(BlockingOSCUDPServer):
    """Blocking OSC UDP server with SO_REUSEPORT + SO_BROADCAST set before bind."""

    def server_bind(self) -> None:
        if hasattr(socket, "SO_REUSEPORT"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
