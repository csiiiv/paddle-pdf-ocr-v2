#!/usr/bin/env python3
"""Serve the repository root and print a v2 viewer URL."""

from __future__ import annotations

import argparse
from functools import partial
import http.server
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parent


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Static handler with the byte ranges PDF.js needs for large documents."""

    byte_range: tuple[int, int] | None = None

    def end_headers(self) -> None:
        if self.path.split("?", 1)[0].lower().endswith(".pdf"):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        self.byte_range = None
        range_header = self.headers.get("Range")
        path = Path(self.translate_path(self.path))
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header or "")
        if not match or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        start = int(match.group(1) or 0)
        end = min(int(match.group(2) or size - 1), size - 1)
        if start > end or start >= size:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None
        stream = path.open("rb")
        self.send_response(206)
        self.send_header("Content-type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(path.stat().st_mtime))
        self.end_headers()
        stream.seek(start)
        self.byte_range = (start, end)
        return stream

    def copyfile(self, source, outputfile) -> None:
        if self.byte_range is None:
            try:
                return super().copyfile(source, outputfile)
            except (BrokenPipeError, ConnectionResetError):
                return None
        remaining = self.byte_range[1] - self.byte_range[0] + 1
        while remaining:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            try:
                outputfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            remaining -= len(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8872)
    parser.add_argument("--run", default="NEP-2027-VOLUME-2B_OCR")
    parser.add_argument("--page", type=int, default=13)
    parser.add_argument(
        "--react", action="store_true",
        help="Serve the built viewer-react/dist application instead of viewer/",
    )
    args = parser.parse_args()
    viewer_path = "viewer-react/dist/" if args.react else "viewer/"
    url = f"http://127.0.0.1:{args.port}/paddle_pdf_ocr_v2/{viewer_path}?run={args.run}&page={args.page}&panel=tokens"
    print(url, flush=True)
    handler = partial(RangeRequestHandler, directory=REPO)
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
