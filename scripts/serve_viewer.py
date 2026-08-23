#!/usr/bin/env python3
"""Serve the repository root and print a v2 viewer URL."""

from __future__ import annotations

import argparse
import http.server
import socketserver
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8872)
    parser.add_argument("--run", default="extraction-smoke")
    parser.add_argument("--page", type=int, default=13)
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}/paddle_pdf_ocr_v2/viewer/?run={args.run}&page={args.page}&panel=tokens"
    print(url, flush=True)
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=REPO, **kw)
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
