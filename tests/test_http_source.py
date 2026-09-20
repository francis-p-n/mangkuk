"""The HTTP path, which is how the organizers' docker server is read.

This is the one part of the pipeline whose failures are not in the documents:
a stalled connection, a 503, a hostname that resolves to a stack nothing is
listening on. None of those show up reading the local bundle, and all of them
show up on the day, so they are exercised here against a real socket rather
than a mock.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sdoc.documents import extract
from sdoc.mailsource import HttpMailSource, open_source, BundleMailSource

EMAIL = {"email_id": "email_001", "from": "a@b.com", "subject": "s",
         "body": "b", "attachments": ["attachments/email_001_SI.txt"]}
BODY = b"SHIPPING INSTRUCTION\nShipper: ALPHA TRADING\n"


class Script:
    """How the next few requests should behave."""

    def __init__(self):
        self.fail_times = 0     # answer 503 this many times, then succeed
        self.hang = False       # accept the request and never answer
        self.requests = 0


SCRIPT = Script()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        SCRIPT.requests += 1
        if SCRIPT.hang:
            threading.Event().wait(30)
            return
        if SCRIPT.fail_times > 0:
            SCRIPT.fail_times -= 1
            return self._json({"error": "busy"}, code=503)

        if self.path == "/emails":
            return self._json([EMAIL])
        if self.path == "/sample_submission":
            return self._json({"email_001": {}})
        if self.path.startswith("/attachments/"):
            self.send_response(200)
            self.send_header("Content-Length", str(len(BODY)))
            self.end_headers()
            self.wfile.write(BODY)
            return
        self._json({"error": "nope"}, code=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        sent = json.loads(self.rfile.read(length))
        self._json({"accepted": len(sent), "final_score": 0.5})


@pytest.fixture(autouse=True)
def quick_retries(monkeypatch):
    """The backoff is real behaviour, but waiting for it in a test only
    measures time.sleep. The number of attempts is what matters here."""
    monkeypatch.setattr(HttpMailSource, "BACKOFF", 0.0)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    SCRIPT.fail_times, SCRIPT.hang, SCRIPT.requests = 0, False, 0
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


class TestTheHappyPath:
    def test_emails_are_read(self, server):
        emails = HttpMailSource(server).emails()
        assert [e.email_id for e in emails] == ["email_001"]

    def test_attachments_are_read(self, server):
        assert HttpMailSource(server).read_bytes("attachments/email_001_SI.txt") == BODY

    def test_the_sample_comes_from_the_server(self, server):
        assert HttpMailSource(server).sample_submission() == {"email_001": {}}

    def test_a_submission_is_posted(self, server):
        assert HttpMailSource(server).submit({"a": 1})["final_score"] == 0.5

    def test_open_source_picks_the_http_implementation(self, server, data_dir):
        assert isinstance(open_source(server), HttpMailSource)
        assert isinstance(open_source(str(data_dir)), BundleMailSource)


class TestItSurvivesABadNetwork:
    def test_a_transient_failure_is_retried(self, server):
        SCRIPT.fail_times = 2
        assert HttpMailSource(server).read_bytes("attachments/email_001_SI.txt") == BODY
        assert SCRIPT.requests == 3, "should have taken three goes"

    def test_it_gives_up_rather_than_looping(self, server):
        SCRIPT.fail_times = 99
        with pytest.raises(IOError):
            HttpMailSource(server).emails()
        assert SCRIPT.requests == HttpMailSource.ATTEMPTS

    def test_a_404_is_not_retried(self, server):
        """A missing file is an answer, not a blip."""
        with pytest.raises(Exception):
            HttpMailSource(server).read_bytes("nope/missing.txt")
        assert SCRIPT.requests == 1

    def test_a_stalled_server_times_out_instead_of_hanging(self, server):
        SCRIPT.hang = True
        source = HttpMailSource(server, timeout=0.4)
        source.ATTEMPTS = 1
        with pytest.raises(IOError):
            source.emails()


class TestAFailedFetchIsNotAnUnreadableDocument:
    """The distinction that stops a network blip being reported as a fact
    about a document - and quietly swallowing whatever defect it held."""

    def test_the_document_says_the_bytes_never_arrived(self, server):
        SCRIPT.fail_times = 99
        doc = extract(HttpMailSource(server), "attachments/email_001_SI.txt")
        assert not doc.ok
        assert doc.error == "fetch_failed"

    def test_a_document_that_did_arrive_is_read_normally(self, server):
        doc = extract(HttpMailSource(server), "attachments/email_001_SI.txt")
        assert doc.ok and doc.error is None


class TestLocalhostIsPinnedToAWorkingStack:
    """On Windows `localhost` offers ::1 first. Against a server bound only to
    IPv4 every request pays the failed IPv6 attempt - about two seconds, which
    turns a five-second run into a nine-minute one. The organizers' own
    instructions say `http://localhost:8080`."""

    def test_localhost_is_replaced_with_an_address_that_answers(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            source = HttpMailSource(f"http://localhost:{srv.server_address[1]}")
            assert "localhost" not in source.base
            assert source.emails()[0].email_id == "email_001"
        finally:
            srv.shutdown()
            srv.server_close()

    def test_a_real_hostname_is_left_alone(self):
        assert HttpMailSource("http://example.invalid:8080").base == \
            "http://example.invalid:8080"

    def test_an_unreachable_localhost_still_yields_a_usable_url(self):
        """Nothing listening is not this function's problem to solve; it must
        hand back something the caller can fail on normally."""
        assert HttpMailSource("http://localhost:9").base.startswith("http://")
