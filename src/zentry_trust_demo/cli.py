from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from zentry_trust_demo.common import load_context
from zentry_trust_demo.zitify_http import HttpBind, run_traditional_http_server, run_zitified_http_server, ziti_http_get
from zentry_trust_demo.traditional import TcpTarget, run_echo_client, run_echo_server
from zentry_trust_demo.ziti_echo import run_ziti_echo_client, run_ziti_echo_host
from zentry_trust_demo.ziti_proxy import ProxyBind, run_ziti_http_proxy


def _add_traditional(sub: argparse._SubParsersAction) -> None:
    srv = sub.add_parser("traditional-server", help="Run a public TCP echo server")
    srv.add_argument("--bind", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=9000)

    cli = sub.add_parser("traditional-client", help="Call the public TCP echo server")
    cli.add_argument("--host", default="127.0.0.1")
    cli.add_argument("--port", type=int, default=9000)
    cli.add_argument("--message", default="hello")


def _add_ziti(sub: argparse._SubParsersAction) -> None:
    host = sub.add_parser("ziti-host", help="Host an echo service over OpenZiti")
    host.add_argument("--identity", required=True, help="Path to enrolled identity JSON (e.g. ZentrySentinel.json)")
    host.add_argument("--service", required=True, help="Ziti service name (must exist on controller)")

    cli = sub.add_parser("ziti-client", help="Call the echo service over OpenZiti")
    cli.add_argument("--identity", required=True, help="Path to enrolled identity JSON (e.g. ZentryClient.json)")
    cli.add_argument("--service", required=True, help="Ziti service name (must exist on controller)")
    cli.add_argument("--message", default="hello")


def _add_http(sub: argparse._SubParsersAction) -> None:
    srv = sub.add_parser("traditional-http-server", help="Run a public HTTP server")
    srv.add_argument("--bind", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8080)

    ghost = sub.add_parser("zitify-http-server", help="Run an HTTP server bound to a Ziti service (monkeypatch)")
    ghost.add_argument("--identity", required=True, help="Path to enrolled identity JSON (e.g. ZentrySentinel.json)")
    ghost.add_argument("--service", required=True, help="Ziti service name (must exist on controller)")
    ghost.add_argument("--bind", default="127.0.0.1")
    ghost.add_argument("--port", type=int, default=8080)

    cli = sub.add_parser("ziti-http-get", help="Send a basic HTTP GET over a Ziti service")
    cli.add_argument("--identity", required=True, help="Path to enrolled identity JSON (e.g. ZentryClient.json)")
    cli.add_argument("--service", required=True, help="Ziti service name (must exist on controller)")
    cli.add_argument("--path", default="/")

    proxy = sub.add_parser("ziti-http-proxy", help="Expose a local port that forwards HTTP over a Ziti service")
    proxy.add_argument("--identity", required=True, help="Path to enrolled identity JSON (e.g. ZentryClient.json)")
    proxy.add_argument("--service", default="ZentryWeb", help="Ziti service name (default: ZentryWeb)")
    proxy.add_argument("--bind", default="127.0.0.1")
    proxy.add_argument("--port", type=int, default=8080)


def _add_demo(sub: argparse._SubParsersAction) -> None:
    demo = sub.add_parser(
        "demo",
        help="One-shot demo: bring up lab, configure Ziti, and run an invisible HTTP service",
    )
    demo_sub = demo.add_subparsers(dest="action", required=True)

    up = demo_sub.add_parser("up", help="Start quickstart, create identities/service, and launch Sentinel HTTP server")
    up.add_argument(
        "--service",
        default="ZentryWeb",
        help="Ziti service name to use for the demo (default: ZentryWeb)",
    )

    connect = demo_sub.add_parser("connect", help="Use the demo client identity to GET / over the Ziti service")
    connect.add_argument(
        "--service",
        default="ZentryWeb",
        help="Ziti service name to use for the demo (default: ZentryWeb)",
    )


def _add_shortcuts(sub: argparse._SubParsersAction) -> None:
    """Top-level shortcuts so you can run `zentry up` and `zentry connect`.

    These are thin aliases for `demo up` and `demo connect`.
    """

    # 'up' and ultra-short 'u'
    for cmd in ["up", "u"]:
        up = sub.add_parser(cmd, help="Start the Zentry-Trust demo (same as: demo up)")
        up.add_argument(
            "--service",
            default="ZentryWeb",
            help="Ziti service name to use for the demo (default: ZentryWeb)",
        )

    # 'connect' and ultra-short 'c'
    for cmd in ["connect", "c"]:
        connect = sub.add_parser(cmd, help="Connect to the demo service (same as: demo connect)")
        connect.add_argument(
            "--service",
            default="ZentryWeb",
            help="Ziti service name to use for the demo (default: ZentryWeb)",
        )

    # 'http' and ultra-short 'h'
    for cmd in ["http", "h"]:
        http = sub.add_parser(cmd, help="Access the ghost app in your browser (opens a local Ziti tunnel)")
        http.add_argument("--bind", default="127.0.0.1")
        http.add_argument("--port", type=int, default=8080)
        http.add_argument(
            "--service",
            default="ZentryWeb",
            help="Ziti service name to use for the demo (default: ZentryWeb)",
        )
        http.add_argument(
            "--identity",
            default="ZentryClient.json",
            help="Path to enrolled client identity JSON (default: ZentryClient.json)",
        )

    # 'proxy' and ultra-short 'p'
    for cmd in ["proxy", "p"]:
        proxy = sub.add_parser(cmd, help="Alias for 'http' (opens a local Ziti tunnel)")
        proxy.add_argument("--bind", default="127.0.0.1")
        proxy.add_argument("--port", type=int, default=8080)
    proxy.add_argument(
        "--service",
        default="ZentryWeb",
        help="Ziti service name to use for the demo (default: ZentryWeb)",
    )
    proxy.add_argument(
        "--identity",
        default="ZentryClient.json",
        help="Path to enrolled client identity JSON (default: ZentryClient.json)",
    )


def _project_root() -> Path:
    # src/zentry_trust_demo/cli.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _run_step(desc: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"[demo] {desc} -> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd), env=env)
    if result.returncode != 0:
        print(f"[demo] FAILED: {desc} (exit code {result.returncode})", file=sys.stderr)
        raise SystemExit(result.returncode)


def _demo_up(service: str) -> int:
    root = _project_root()
    compose = root / "zentry-trust" / "compose.yml"
    scripts_dir = root / "scripts"
    env = os.environ.copy()
    # Use sensible lab defaults so users don't have to export env vars.
    env.setdefault("ZITI_PWD", "admin")
    # For the self-contained demo we always start from a clean quickstart volume.
    env.setdefault("ZITI_RESET", "1")
    env.setdefault("ZITI_COMPOSE_FILE", str(compose))

    # 1) Ensure quickstart is up and identities exist
    step2 = scripts_dir / "ziti_step2_identities_quickstart.sh"
    if not step2.is_file():
        print(f"ERROR: missing script: {step2}", file=sys.stderr)
        return 1

    _run_step("creating Sentinel/Client identities (and starting quickstart)", ["bash", str(step2)], cwd=root, env=env)

    # 2) Enroll identities on this machine for the demo
    enroll = scripts_dir / "ziti_step2_enroll_quickstart.sh"
    if not enroll.is_file():
        print(f"ERROR: missing script: {enroll}", file=sys.stderr)
        return 1

    _run_step(
        "enrolling Sentinel identity",
        ["bash", str(enroll), "ZentrySentinel.jwt", "ZentrySentinel.json"],
        cwd=root,
        env=env,
    )
    _run_step(
        "enrolling Client identity",
        ["bash", str(enroll), "ZentryClient.jwt", "ZentryClient.json"],
        cwd=root,
        env=env,
    )

    # 3) Create the demo service and policies
    step3 = scripts_dir / "ziti_step3_service_policies.sh"
    if not step3.is_file():
        print(f"ERROR: missing script: {step3}", file=sys.stderr)
        return 1
    print(f"[demo] creating {service} service + policies -> bash {step3}")
    result = subprocess.run(["bash", str(step3)], cwd=str(root), env=env)
    if result.returncode != 0:
        print(f"[demo] FAILED: creating {service} service + policies (exit code {result.returncode})", file=sys.stderr)
        return result.returncode

    # 4) Start the Sentinel HTTP server bound to the Ziti service
    print("[demo] starting Sentinel HTTP server via zitify-http-server ...")
    sentinel_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "zentry_trust_demo.cli",
            "zitify-http-server",
            "--identity",
            "ZentrySentinel.json",
            "--service",
            service,
        ],
        cwd=str(root),
    )
    print(f"[demo] Sentinel HTTP server running in background (PID {sentinel_proc.pid}).")

    # 5) Quick policy-advisor check for the service
    print("[demo] checking policy-advisor status for services ...")
    pa = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose),
            "exec",
            "-T",
            "quickstart",
            "ziti",
            "edge",
            "policy-advisor",
            "services",
            "-q",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if pa.returncode == 0:
        print(pa.stdout.strip())
    else:
        print("[demo] WARNING: policy-advisor failed; check your controller logs.", file=sys.stderr)
        if pa.stderr:
            print(pa.stderr.strip(), file=sys.stderr)

    print()
    print("="*60)
    print("✓ Zentry-Trust is LIVE")
    print("="*60)
    print()
    print("Your app is now DARK (no public port exposed).")
    print("Only authorized identities can reach it via Ziti.")
    print()
    print("To access in your browser:")
    print("  1. In a NEW terminal, run: zentry h")
    print("     (Starts proxy at http://127.0.0.1:8080/)")
    print("  2. Open browser to: http://127.0.0.1:8080/")
    print()
    print("Or test from CLI: zentry c      (or 'zentry connect')")
    print()
    return 0


def _demo_connect(service: str) -> int:
    root = _project_root()
    client_identity = root / "ZentryClient.json"
    if not client_identity.is_file():
        print(
            f"ERROR: client identity not found at {client_identity}. "
            "Run 'zentrytrust demo up' first.",
            file=sys.stderr,
        )
        return 1

    ctx = load_context(str(client_identity))
    data = ziti_http_get(ctx, service, "/")
    sys.stdout.buffer.write(data)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="zentrytrust",
        description=(
            "Demonstrate Traditional (public TCP) vs Zentry-Trust (OpenZiti) access. "
            "Traditional uses a reachable IP:port; Ziti uses identity + service name with no public listener."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_traditional(sub)
    _add_ziti(sub)
    _add_http(sub)
    _add_shortcuts(sub)
    _add_demo(sub)

    args = parser.parse_args(argv)

    if args.cmd == "traditional-server":
        run_echo_server(TcpTarget(args.bind, args.port))
        return 0

    if args.cmd == "traditional-client":
        data = run_echo_client(TcpTarget(args.host, args.port), args.message.encode("utf-8"))
        print(data.decode("utf-8", errors="replace"))
        return 0

    if args.cmd == "ziti-host":
        ctx = load_context(args.identity)
        run_ziti_echo_host(ctx, args.service)
        return 0

    if args.cmd == "ziti-client":
        ctx = load_context(args.identity)
        data = run_ziti_echo_client(ctx, args.service, args.message.encode("utf-8"))
        print(data.decode("utf-8", errors="replace"))
        return 0

    if args.cmd == "traditional-http-server":
        run_traditional_http_server(HttpBind(args.bind, args.port))
        return 0

    if args.cmd == "zitify-http-server":
        run_zitified_http_server(args.identity, args.service, HttpBind(args.bind, args.port))
        return 0

    if args.cmd == "ziti-http-get":
        ctx = load_context(args.identity)
        data = ziti_http_get(ctx, args.service, args.path)
        sys.stdout.buffer.write(data)
        return 0

    if args.cmd == "ziti-http-proxy":
        run_ziti_http_proxy(args.identity, args.service, ProxyBind(args.bind, args.port))
        return 0
    if args.cmd in ("http", "h"):
        run_ziti_http_proxy(args.identity, args.service, ProxyBind(args.bind, args.port))
        return 0
    if args.cmd in ("proxy", "p"):
        run_ziti_http_proxy(args.identity, args.service, ProxyBind(args.bind, args.port))
        return 0

    if args.cmd in ("up", "u"):
        return _demo_up(args.service)

    if args.cmd in ("connect", "c"):
        return _demo_connect(args.service)

    if args.cmd == "demo":
        if args.action == "up":
            return _demo_up(args.service)
        if args.action == "connect":
            return _demo_connect(args.service)

        print(f"Unknown demo action: {args.action}", file=sys.stderr)
        return 2

    print(f"Unknown command: {args.cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
