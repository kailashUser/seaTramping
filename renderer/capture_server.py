"""
Static file server for the voyage renderer, plus a frame sink.

Two jobs:

  GET  /...           serve the renderer, vendor bundle and data
  POST /frame?name=X  write a PNG posted by the page into frames/

The POST endpoint lets the browser hand rendered frames back to disk, which is
how the MP4 is produced deterministically: the page steps to an exact video
time, renders, and posts the result, so the output does not depend on real-time
frame pacing the way a screen recording does.

    python renderer/capture_server.py [port]
"""

import base64
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
FRAME_DIR = os.path.join(_HERE, "frames")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=_ROOT, **kwargs)

    def log_message(self, fmt, *args):
        # Per-frame POSTs would otherwise flood the console.
        if "/frame" not in (self.path or ""):
            super().log_message(fmt, *args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/frame":
            self.send_error(404)
            return

        name = (parse_qs(parsed.query).get("name") or ["frame"])[0]
        # Never let a posted name escape the frame directory.
        name = os.path.basename(name)
        if not name.endswith(".png"):
            name += ".png"

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if body[:22].startswith(b"data:image/png;base64,"):
            body = base64.b64decode(body[22:])

        os.makedirs(FRAME_DIR, exist_ok=True)
        with open(os.path.join(FRAME_DIR, name), "wb") as f:
            f.write(body)

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    os.makedirs(FRAME_DIR, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"serving {_ROOT} on http://127.0.0.1:{port}")
    print(f"frames -> {FRAME_DIR}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
