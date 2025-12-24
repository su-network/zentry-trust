from __future__ import annotations

import socket
import threading

import openziti
from openziti import zitilib


def run_ziti_echo_host(ctx: openziti.ZitiContext, service: str, backlog: int = 128) -> None:
    """Host an echo service over OpenZiti.

    This binds to a *Ziti service name* (not an IP:port) so there is no public listener.
    """
    srv_fd = zitilib.ziti_socket(socket.SOCK_STREAM)
    zitilib.bind(srv_fd, ctx._ctx, service=service)
    zitilib.listen(srv_fd, backlog)

    print(f"[ziti] hosting service {service!r} (no public TCP listener)")

    def handle_client(client: socket.socket) -> None:
        with client:
            while True:
                data = client.recv(4096)
                if not data:
                    return
                client.sendall(data)

    while True:
        client_fd, _peer = zitilib.accept(srv_fd)
        client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0, client_fd)
        threading.Thread(target=handle_client, args=(client_sock,), daemon=True).start()


def run_ziti_echo_client(ctx: openziti.ZitiContext, service: str, message: bytes) -> bytes:
    """Connect to a Ziti service and echo a message."""
    with ctx.connect(service) as s:
        s.sendall(message)
        return s.recv(4096)
