"""One class per provider, behind a single method.

Swapping provider is a new class here and nothing else. The grounding checks
downstream mean a weaker model can only abstain, never do damage.
"""
from __future__ import annotations

import json
import os
import random
import time
from typing import Protocol

DEFAULT_MODEL = os.environ.get("SDOC_MODEL", "claude-opus-5")
BEDROCK_MODEL = os.environ.get("SDOC_BEDROCK_MODEL", "anthropic.claude-opus-5")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# A full run asks for one call per abstained classification and one per
# document the parsers could not read - 72 against the supplied bundle. On a
# free tier that is well past the per-minute allowance, so being rate limited
# is the expected case, not the exceptional one.
MAX_RETRIES = int(os.environ.get("SDOC_MAX_RETRIES", "5"))


class RateLimited(RuntimeError):
    """The provider never answered, because we asked too fast.

    Kept apart from every other failure for the same reason a document that
    never arrived is kept apart from one that could not be read: an answer of
    "nothing" and no answer at all are different facts, and only the first is
    the agent's opinion. Collapsing them makes a throttled run look like a
    model that found nothing, which is the wrong thing to conclude and the
    wrong thing to fix.
    """


class LLMClient(Protocol):
    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str: ...


class NullClient:
    """Stands in when no model is configured. Always abstains."""

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        return ""


class AnthropicClient:
    """First-party Claude API.

    The SDK already retries 429 and 5xx with exponential backoff, so the only
    thing to do here is raise its allowance and let it do the waiting. Adding
    our own loop on top would multiply the attempts and the delay.
    """

    def __init__(self, model: str = DEFAULT_MODEL, max_retries: int = MAX_RETRIES):
        import anthropic

        self._client = anthropic.Anthropic(max_retries=max_retries)
        self._errors = anthropic
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": user}],
            )
        except self._errors.RateLimitError as exc:
            # The SDK has already backed off and retried this far.
            raise RateLimited(f"rate limited after {MAX_RETRIES} retries") from exc
        return "".join(b.text for b in response.content if b.type == "text")


class BedrockClient:
    """Claude on Amazon Bedrock, so document text stays inside the tenant.

    Uses the Mantle client from the anthropic SDK rather than raw boto3
    InvokeModel — same messages surface as the first-party client.
    """

    def __init__(self, model: str = BEDROCK_MODEL, region: str = AWS_REGION,
                 max_retries: int = MAX_RETRIES):
        import anthropic
        from anthropic import AnthropicBedrockMantle

        self._client = AnthropicBedrockMantle(aws_region=region, max_retries=max_retries)
        self._errors = anthropic
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": user}],
            )
        except self._errors.RateLimitError as exc:
            raise RateLimited(f"rate limited after {MAX_RETRIES} retries") from exc
        return "".join(b.text for b in response.content if b.type == "text")


class AgentUnavailable(RuntimeError):
    """Raised at startup so a misconfigured agent fails loudly, not silently."""


GEMINI_MODEL = os.environ.get("SDOC_GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_ENDPOINT = os.environ.get(
    "SDOC_GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/models"
)


def _retry_after(exc) -> float | None:
    """How long the server asked us to wait, if it said.

    Honoured rather than guessed: the server knows when the window resets and
    a guess that is too short just burns another attempt against the limit.
    """
    raw = None
    try:
        raw = exc.headers.get("Retry-After")
    except Exception:
        return None
    if not raw:
        return None
    try:
        # Seconds is the only form these APIs send; an HTTP-date would need
        # parsing and clock-skew handling for no practical gain.
        return max(0.0, min(float(raw), 120.0))
    except ValueError:
        return None


# Gemini 3.x spends tokens on hidden reasoning before it writes anything, and
# that spend counts against maxOutputTokens. Below this the model can burn the
# whole budget thinking and return a candidate with no `parts` at all, which
# is indistinguishable from a genuine abstention. Measured: ~120 thinking
# tokens for a one-word reply, so leave room for a real answer on top.
GEMINI_MIN_OUTPUT_TOKENS = 512


def _daily_quota(exc) -> bool:
    """Is this 429 a per-day cap rather than a per-minute one?

    The two look identical in the status code and the free tier sends a
    `retryDelay` of a few seconds for both, which is honest about when the
    next request is allowed and misleading about when it would succeed.
    Google names the quota in the error body, so read it there.

    Reading the body consumes it and it cannot be put back - the stream is
    closed once drained - so the text is cached on the exception instead.
    Anything downstream that wants the body reads it from there rather than
    from a stream this function has already emptied.
    """
    raw = getattr(exc, "_body", None)
    if raw is None:
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:
            raw = ""
        try:
            exc._body = raw
        except Exception:                 # some exceptions refuse attributes
            pass
    return "PerDay" in raw or "per day" in raw.lower()


def _gemini_text(payload: dict) -> str:
    """Pull the reply text out of a generateContent response.

    Defensive on purpose: a blocked or empty candidate has no `parts`, and the
    resolver treats an empty string as an abstention rather than an error.

    Truncation is the one case that must not look like an abstention. A
    candidate cut off by MAX_TOKENS answered nothing because it ran out of
    room, not because it had nothing to say, and silently scoring that as
    "no opinion" would quietly drop real answers from the run.
    """
    for candidate in payload.get("candidates") or []:
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if text:
            return text
        if candidate.get("finishReason") == "MAX_TOKENS":
            raise RuntimeError(
                "gemini returned no text: the output budget was consumed by "
                "reasoning tokens before any answer was written - raise "
                "max_tokens for this call"
            )
    return ""


class GeminiClient:
    """Google Gemini over the REST API.

    Plain HTTPS through the standard library rather than another SDK: the
    request is one JSON object and this keeps the dependency list honest.
    Set GEMINI_API_KEY, and SDOC_GEMINI_MODEL if your key serves a different
    model name than the default.
    """

    def __init__(self, model: str = GEMINI_MODEL, api_key: str | None = None):
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.model = model
        self._url = f"{GEMINI_ENDPOINT}/{model}:generateContent"
        self._key = key

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """One call, retried on throttling and on transient server faults.

        There is no SDK here to inherit a retry policy from, so this is the
        one provider where the loop has to be written out. It waits as long
        as the server asks when it says so, and backs off exponentially with
        jitter when it does not - unsynchronised, so a burst of calls does
        not retry in lockstep and re-create the burst.
        """
        import urllib.error
        import urllib.request

        body = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": max(max_tokens, GEMINI_MIN_OUTPUT_TOKENS),
                "temperature": 0,
            },
        }).encode("utf-8")

        last: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            request = urllib.request.Request(
                self._url,
                data=body,
                headers={"Content-Type": "application/json",
                         "x-goog-api-key": self._key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return _gemini_text(json.loads(response.read()))
            except urllib.error.HTTPError as exc:
                if exc.code != 429 and exc.code < 500:
                    raise           # a bad key or a bad request; waiting will not help
                last = exc
                if exc.code == 429 and _daily_quota(exc):
                    # A per-day cap does not clear before tomorrow, whatever
                    # the server's Retry-After says. Sleeping through the
                    # backoff once per call is a quarter-hour of nothing on a
                    # full run, and the answer is the same at the end of it.
                    raise RateLimited(
                        "daily quota exhausted for this model - the limit "
                        "resets tomorrow, so retrying now cannot help"
                    ) from exc
                wait = _retry_after(exc) if exc.code == 429 else None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                wait = None

            if attempt >= MAX_RETRIES:
                break
            if wait is None:
                wait = min(2.0 ** attempt, 32.0) + random.uniform(0, 0.5)
            time.sleep(wait)

        raise RateLimited(
            f"no answer after {MAX_RETRIES + 1} attempts: {last}") from last


def make_client(provider: str) -> LLMClient:
    """Build a client, or explain clearly why it cannot be built.

    Failing at startup is deliberate. A silent fallback to NullClient would
    look like a clean run in which the agent simply found nothing.
    """
    if provider == "off":
        return NullClient()

    builders = {
        "bedrock": BedrockClient,
        "anthropic": AnthropicClient,
        "gemini": GeminiClient,
    }
    if provider not in builders:
        raise AgentUnavailable(f"unknown agent provider {provider!r}")

    try:
        return builders[provider]()
    except ImportError as exc:
        raise AgentUnavailable(
            "the anthropic SDK is not installed - run: pip install anthropic"
        ) from exc
    except Exception as exc:
        hint = {
            "bedrock": "check AWS credentials and AWS_REGION, and that the model is "
                       f"enabled in Bedrock ({BEDROCK_MODEL})",
            "anthropic": "check ANTHROPIC_API_KEY",
            "gemini": "check GEMINI_API_KEY, and SDOC_GEMINI_MODEL if your key serves "
                      f"a different model name than {GEMINI_MODEL}",
        }[provider]
        raise AgentUnavailable(f"{type(exc).__name__}: {exc} - {hint}") from exc
