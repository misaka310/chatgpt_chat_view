#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import socket
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def find_free_port(start: int) -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free local port")


def serve(path: Path, port: int, page: str) -> None:
    if not (path / page).exists():
        raise SystemExit(f"missing {path / page}. Run start.bat first.")
    port = find_free_port(port)
    os.chdir(path)
    server = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    url = f"http://127.0.0.1:{port}/{page}"
    print(f"Open this URL: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--port", type=int, default=8733)
    parser.add_argument("--page", default="dashboard.html")
    args = parser.parse_args()
    serve(args.output_dir.resolve(), args.port, args.page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
