"""Serve web/ with the cross-origin-isolation headers WASM threads need.

Plain `python -m http.server` works too, but without COOP/COEP the page has no
SharedArrayBuffer and onnxruntime-web falls back to one thread.

    python serve.py [port]
"""

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main(port=8092):
    root = Path(__file__).resolve().parent / "web"
    server = ThreadingHTTPServer(
        ("127.0.0.1", int(port)), partial(Handler, directory=str(root)))
    print(f"http://127.0.0.1:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main(*sys.argv[1:])
