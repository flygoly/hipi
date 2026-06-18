#!/usr/bin/env python3
"""Minimal HTTP server to test HiPi SMS webhook forwarding and HMAC verification."""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# Allow running from repo root without install
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hipi.webhook import verify_webhook_request  # noqa: E402


class WebhookHandler(BaseHTTPRequestHandler):
    secret: str = ""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        headers = {k: v for k, v in self.headers.items()}

        if self.secret:
            if not verify_webhook_request(self.secret, body, headers):
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"invalid signature\n")
                print("REJECT invalid signature", file=sys.stderr)
                return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"invalid json\n")
            return

        print(json.dumps(payload, ensure_ascii=False, indent=2))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}\n')

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="HiPi webhook test receiver")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--secret",
        default=os.environ.get("HIPI_WEBHOOK_SECRET", ""),
        help="Shared HMAC secret (or set HIPI_WEBHOOK_SECRET)",
    )
    args = parser.parse_args()

    WebhookHandler.secret = args.secret
    server = HTTPServer((args.host, args.port), WebhookHandler)
    mode = "signed" if args.secret else "unsigned"
    print(f"Listening on http://{args.host}:{args.port}/ ({mode})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
