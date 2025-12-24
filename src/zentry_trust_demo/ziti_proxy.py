from __future__ import annotations

import select
import socketserver
from dataclasses import dataclass

from zentry_trust_demo.common import load_context


@dataclass(frozen=True)
class ProxyBind:
    host: str
    port: int


class _ZitiHttpProxyHandler(socketserver.BaseRequestHandler):
    """TCP-level HTTP proxy: browser <-> Ziti service.

    For each incoming TCP connection, we open a Ziti connection to the
    configured service and simply shuttle bytes in both directions. This keeps
    HTTP semantics transparent to both sides.
    """

    def handle(self) -> None:  # type: ignore[override]
        server = self.server  # type: ignore[assignment]
        ctx = server.ctx  # type: ignore[attr-defined]
        service = server.service  # type: ignore[attr-defined]

        try:
            with ctx.connect(service) as zsock:
                # Bidirectional forwarding using select for proper HTTP support
                sockets = [self.request, zsock]
                while True:
                    readable, _, exceptional = select.select(sockets, [], sockets, 30.0)
                    
                    if exceptional:
                        break
                    
                    if not readable:
                        # Timeout - close idle connection
                        break
                    
                    for sock in readable:
                        try:
                            data = sock.recv(4096)
                            if not data:
                                return
                            
                            # Forward data to the other side
                            if sock is self.request:
                                zsock.sendall(data)
                            else:
                                self.request.sendall(data)
                        except Exception:
                            return
        except Exception:
            # This is a demo proxy; ignore per-connection errors.
            return


class _ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def run_ziti_http_proxy(identity_path: str, service: str, bind: ProxyBind) -> None:
    """Expose a local TCP port that forwards HTTP over a Ziti service.

    After this is running you can open http://host:port/ in a browser and the
    traffic will be tunneled through OpenZiti to the ghost HTTP server.
    """

    ctx = load_context(identity_path)

    with _ThreadingTCPServer((bind.host, bind.port), _ZitiHttpProxyHandler) as server:
        server.ctx = ctx  # type: ignore[attr-defined]
        server.service = service  # type: ignore[attr-defined]
        print(
            f"[proxy] listening on http://{bind.host}:{bind.port} "
            f"and forwarding to Ziti service {service!r}"
        )
        server.serve_forever()
