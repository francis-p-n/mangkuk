"""What happens when the provider will not answer.

A run asks for 72 calls against the supplied bundle. On a free tier most of
them come back 429, and the failure that matters is not the throttling - it
is what the throttling looks like afterwards. A rate-limited call and a model
that read the document and found nothing produce the same submission, so if
they are counted the same the obvious conclusion is "the prompt is bad" and
the obvious fix is to rewrite a prompt that was never run.

So these tests are mostly about bookkeeping: that silence is counted as
silence, and that the run says so.
"""
from __future__ import annotations

import json
import sys
import threading
import types
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sdoc.agents import (
    MAX_RETRIES, AgentStats, FieldResolver, GeminiClient, RateLimited,
    TriageAgent, _retry_after,
)
from sdoc.fields import FieldSet

GOOD = {"candidates": [{"content": {"parts": [{"text": '{"category": "SPAM"}'}]}}]}


class Script:
    def __init__(self):
        self.status = 200        # what to answer with until fail_times runs out
        self.fail_times = 0
        self.retry_after: str | None = None
        self.requests = 0


SCRIPT = Script()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        SCRIPT.requests += 1
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if SCRIPT.fail_times > 0:
            SCRIPT.fail_times -= 1
            body = b'{"error": "too fast"}'
            self.send_response(SCRIPT.status)
            if SCRIPT.retry_after:
                self.send_header("Retry-After", SCRIPT.retry_after)
        else:
            body = json.dumps(GOOD).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Record what the client would have slept instead of sleeping it."""
    slept: list[float] = []
    monkeypatch.setattr("sdoc.agents.clients.time.sleep", slept.append)
    return slept


@pytest.fixture
def gemini():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    SCRIPT.status, SCRIPT.fail_times, SCRIPT.retry_after, SCRIPT.requests = 200, 0, None, 0
    client = GeminiClient(api_key="test-key")
    client._url = f"http://127.0.0.1:{srv.server_address[1]}/generate"
    yield client
    srv.shutdown()
    srv.server_close()


class TestRetryAfterParsing:
    @pytest.mark.parametrize("header,expected", [
        ("30", 30.0),
        ("0", 0.0),
        ("999", 120.0),        # capped - a run should not sit still for 15 minutes
        ("tomorrow", None),    # an HTTP-date is not worth the clock-skew handling
        (None, None),
    ])
    def test_parsing(self, header, expected):
        exc = urllib.error.HTTPError(
            "u", 429, "m", {"Retry-After": header} if header else {}, None)
        assert _retry_after(exc) == expected


class TestGeminiRetries:
    def test_a_429_is_retried_and_then_succeeds(self, gemini):
        SCRIPT.status, SCRIPT.fail_times = 429, 2
        assert "SPAM" in gemini.complete("s", "u")
        assert SCRIPT.requests == 3

    def test_it_waits_as_long_as_the_server_asked(self, gemini, no_waiting):
        SCRIPT.status, SCRIPT.fail_times, SCRIPT.retry_after = 429, 1, "7"
        gemini.complete("s", "u")
        assert no_waiting == [7.0], "should honour Retry-After, not guess"

    def test_without_a_header_it_backs_off_and_jitters(self, gemini, no_waiting):
        SCRIPT.status, SCRIPT.fail_times = 429, 3
        gemini.complete("s", "u")
        assert len(no_waiting) == 3
        assert no_waiting == sorted(no_waiting), "each wait at least as long as the last"
        assert all(w != int(w) for w in no_waiting), "jittered, so calls do not resync"

    def test_giving_up_says_it_was_never_answered(self, gemini):
        SCRIPT.status, SCRIPT.fail_times = 429, 99
        with pytest.raises(RateLimited):
            gemini.complete("s", "u")
        assert SCRIPT.requests == MAX_RETRIES + 1

    def test_a_server_fault_is_retried_too(self, gemini):
        SCRIPT.status, SCRIPT.fail_times = 503, 2
        assert "SPAM" in gemini.complete("s", "u")

    def test_a_bad_request_is_not_retried(self, gemini):
        """A rejected key or a malformed body will be rejected again."""
        SCRIPT.status, SCRIPT.fail_times = 400, 99
        with pytest.raises(urllib.error.HTTPError):
            gemini.complete("s", "u")
        assert SCRIPT.requests == 1


class TestTheSdkClientsInheritTheirOwnRetries:
    """The Anthropic SDK already retries 429 and 5xx with backoff. The job
    here is to raise its allowance, not to wrap a second loop around it."""

    @pytest.fixture
    def fake_anthropic(self, monkeypatch):
        mod = types.ModuleType("anthropic")
        seen = {}

        class RateLimitError(Exception):
            pass

        class Anthropic:
            def __init__(self, **kwargs):
                seen.update(kwargs)
                self.messages = types.SimpleNamespace(
                    create=lambda **kw: (_ for _ in ()).throw(RateLimitError("429")))

        mod.RateLimitError = RateLimitError
        mod.Anthropic = Anthropic
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        return seen

    def test_the_retry_allowance_is_raised(self, fake_anthropic):
        from sdoc.agents.clients import AnthropicClient

        AnthropicClient()
        assert fake_anthropic.get("max_retries") == MAX_RETRIES

    def test_the_sdks_rate_limit_error_becomes_ours(self, fake_anthropic):
        from sdoc.agents.clients import AnthropicClient

        with pytest.raises(RateLimited):
            AnthropicClient().complete("s", "u")


class Throttled:
    """A client that never answers."""

    def complete(self, system, user, max_tokens=1024):
        raise RateLimited("no answer")


class Broken:
    def complete(self, system, user, max_tokens=1024):
        raise ValueError("something else went wrong")


class Quiet:
    """A client that answers, with nothing useful in it."""

    def complete(self, system, user, max_tokens=1024):
        return "{}"


class TestSilenceIsNotAnAbstention:
    """The distinction the whole layer exists for."""

    def test_a_throttled_classification_is_counted_as_silence(self):
        stats = AgentStats()
        assert TriageAgent(Throttled(), stats).classify("s", "b") is None
        assert stats.rate_limited == 1
        assert stats.triage_accepted == 0
        assert stats.incomplete

    def test_an_answered_abstention_is_not(self):
        stats = AgentStats()
        assert TriageAgent(Quiet(), stats).classify("s", "b") is None
        assert stats.rate_limited == 0
        assert not stats.incomplete, "the model answered; it just had no opinion"

    def test_a_throttled_resolution_is_counted_as_silence(self):
        stats = AgentStats()
        FieldResolver(Throttled(), stats).resolve("some text", FieldSet(), "SI")
        assert stats.rate_limited == 1
        assert stats.fields_returned == 0
        assert stats.incomplete

    def test_other_failures_are_counted_apart_from_throttling(self):
        stats = AgentStats()
        TriageAgent(Broken(), stats).classify("s", "b")
        assert (stats.rate_limited, stats.failed) == (0, 1)
        assert stats.incomplete

    def test_the_arithmetic_adds_up(self):
        stats = AgentStats()
        for _ in range(3):
            TriageAgent(Throttled(), stats).classify("s", "b")
        TriageAgent(Quiet(), stats).classify("s", "b")
        assert (stats.calls, stats.answered) == (4, 1)

    def test_a_fully_answered_run_is_not_flagged(self):
        stats = AgentStats()
        TriageAgent(Quiet(), stats).classify("s", "b")
        assert not stats.incomplete


class TestProgress:
    def test_nothing_is_printed_unless_asked(self, capsys):
        TriageAgent(Quiet(), AgentStats()).classify("s", "b")
        assert capsys.readouterr().out == ""

    def test_every_call_reports_where_it_got_to(self):
        lines: list[str] = []
        stats = AgentStats(progress=lines.append)
        TriageAgent(Throttled(), stats).classify("s", "b")
        TriageAgent(Quiet(), stats).classify("s", "b")
        assert len(lines) == 2
        assert "rate limited" in lines[0]
        assert lines[1].startswith("[1/2]"), "progress counts answers, not attempts"

    def test_the_counters_survive_serialisation(self):
        stats = AgentStats(progress=print)
        payload = stats.as_dict()
        assert "progress" not in payload and "notes" not in payload
        assert payload["rate_limited"] == 0
        json.dumps(payload)
