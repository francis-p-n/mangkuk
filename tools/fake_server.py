#!/usr/bin/env python3
"""A stand-in for the organizers' docker server, so the HTTP path is not
first exercised on the day.

    python tools/fake_server.py            # serves data/ on :8080
    python run.py --source http://localhost:8080

It implements the same routes `data/loader.py` calls - `/emails`,
`/emails/<id>`, `/sample_submission`, any `attachments/...` path, and
`/submit` - reading from the local bundle. It is not the real server and
cannot score anything: `/submit` only validates the shape and reports what
was sent, which is the part that can actually be wrong on our side.

Two options exist to rehearse the failure modes that matter more than the
happy path:

    --slow 3        every response waits three seconds (does the client time out?)
    --flaky 0.2     one request in five fails with a 503 (does the run survive?)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdoc.validate import validate  # noqa: E402

CONFIG = {"bundle": ROOT / "data", "slow": 0.0, "flaky": 0.0}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path} -> {args[1]}")

    # -- plumbing ------------------------------------------------------
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

    def _misbehave(self) -> bool:
        """Apply whatever unreliability was asked for. True = already answered."""
        if CONFIG["slow"]:
            time.sleep(CONFIG["slow"])
        if CONFIG["flaky"] and random.random() < CONFIG["flaky"]:
            self._json({"error": "pretending to be overloaded"}, code=503)
            return True
        return False

    # -- routes --------------------------------------------------------
    def do_GET(self):
        if self._misbehave():
            return
        bundle: Path = CONFIG["bundle"]
        path = self.path.split("?")[0].lstrip("/")

        if path == "emails":
            records = [json.loads(p.read_text(encoding="utf-8"))
                       for p in sorted((bundle / "inbox").glob("email_*.json"))]
            return self._json(records)

        if path.startswith("emails/"):
            one = bundle / "inbox" / f"{path.split('/', 1)[1]}.json"
            if not one.exists():
                return self._json({"error": "no such email"}, code=404)
            return self._json(json.loads(one.read_text(encoding="utf-8")))

        if path == "sample_submission":
            return self._json(json.loads(
                (bundle / "sample_submission.json").read_text(encoding="utf-8")))

        if path.startswith("attachments/"):
            # Resolved and then checked, so "attachments/../../secrets" cannot
            # walk out of the bundle even though this only ever runs locally.
            target = (bundle / path).resolve()
            if not target.is_relative_to(bundle.resolve()) or not target.exists():
                return self._json({"error": "no such attachment"}, code=404)
            return self._send(200, target.read_bytes(), "application/octet-stream")

        self._json({"error": f"no route for /{path}"}, code=404)

    def do_POST(self):
        if self._misbehave():
            return
        if self.path.rstrip("/") != "/submit":
            return self._json({"error": "only /submit accepts POST"}, code=404)

        length = int(self.headers.get("Content-Length") or 0)
        try:
            submission = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            return self._json({"error": f"body is not JSON: {exc}"}, code=400)

        problems = validate(submission, CONFIG["bundle"] / "sample_submission.json")
        if problems:
            return self._json({"error": "submission rejected", "problems": problems[:10]},
                              code=400)
        # The real server scores here. This one cannot, and says so rather
        # than inventing a number that would be believed.
        return self._json({
            "accepted": len(submission),
            "final_score": None,
            "note": "stand-in server: shape is valid, scoring needs the real one",
        })


def main() -> int:
    ap = argparse.ArgumentParser(description="stand-in for the organizers' server")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address; ::1 to rehearse an IPv6-only server")
    ap.add_argument("--bundle", default=str(ROOT / "data"))
    ap.add_argument("--slow", type=float, default=0.0, metavar="SECONDS",
                    help="delay every response, to test client timeouts")
    ap.add_argument("--flaky", type=float, default=0.0, metavar="RATE",
                    help="fail this fraction of requests with a 503")
    args = ap.parse_args()

    CONFIG.update(bundle=Path(args.bundle), slow=args.slow, flaky=args.flaky)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {CONFIG['bundle']} on http://localhost:{args.port}")
    if args.slow or args.flaky:
        print(f"  misbehaving on purpose: slow={args.slow}s flaky={args.flaky}")
    print("  python run.py --source http://localhost:%d\n" % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
