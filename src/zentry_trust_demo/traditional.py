from __future__ import annotations

import socket
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class TcpTarget:
    host: str
    port: int


def run_echo_server(bind: TcpTarget) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((bind.host, bind.port))
    server.listen(128)

    print(f"[traditional] listening on tcp://{bind.host}:{bind.port} (publicly reachable if port is exposed)")

    def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
        with conn:
            while True:
                data = conn.recv(4096)
                if not data:
                    return
                conn.sendall(data)

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


def run_echo_client(target: TcpTarget, message: bytes) -> bytes:
    with socket.create_connection((target.host, target.port), timeout=5) as s:
        s.sendall(message)
        return s.recv(4096)
