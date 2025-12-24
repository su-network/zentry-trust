from __future__ import annotations

import http.server
import socket
from dataclasses import dataclass

import openziti


@dataclass(frozen=True)
class HttpBind:
    host: str
    port: int


def run_traditional_http_server(bind: HttpBind) -> None:
    """A plain HTTP server that is visible on the network (traditional model)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b"Welcome to the Traditional Server (public listener)\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:  # noqa: D401
            return

    server = http.server.ThreadingHTTPServer((bind.host, bind.port), Handler)
    print(f"[traditional] HTTP listening on http://{bind.host}:{bind.port} (discoverable if reachable)")
    server.serve_forever()


def run_zitified_http_server(identity_path: str, service: str, bind: HttpBind) -> None:
    """Run a normal Python HTTP server, but bind its socket to a Ziti service.

    The application still binds to (host, port) in code, but `openziti.monkeypatch`
    remaps that bind() to an OpenZiti service name. Result: no public TCP listener.
    """

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b"Welcome to the Zentry-Trust Ghost Server (no public listener)\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:  # noqa: D401
            return

    bindings = {
        (bind.host, bind.port): {
            "ztx": identity_path,
            "service": service,
        }
    }

    # While patched, frameworks that create/bind sockets (Flask/Django/http.server/etc)
    # will bind *inside Ziti* for matching (host, port) pairs.
    with openziti.monkeypatch(bindings=bindings):
        server = http.server.ThreadingHTTPServer((bind.host, bind.port), Handler)
        print(f"[ziti] HTTP bound to service {service!r} via monkeypatch (no public TCP listener)")
        server.serve_forever()


def ziti_http_get(ctx: openziti.ZitiContext, service: str, path: str = "/") -> bytes:
    """Minimal HTTP/1.1 GET over a Ziti service (no intercept config required)."""
    if not path.startswith("/"):
        path = "/" + path

    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {service}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("utf-8")

    with ctx.connect(service) as s:
        s.settimeout(10)
        s.sendall(req)
        chunks: list[bytes] = []
        while True:
            try:
                data = s.recv(4096)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)

    return b"".join(chunks)
