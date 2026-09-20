"""One class per provider, behind a single method.

Swapping provider is a new class here and nothing else. The grounding checks
downstream mean a weaker model can only abstain, never do damage.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

DEFAULT_MODEL = os.environ.get("SDOC_MODEL", "claude-opus-5")
BEDROCK_MODEL = os.environ.get("SDOC_BEDROCK_MODEL", "anthropic.claude-opus-5")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

class LLMClient(Protocol):
    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str: ...


class NullClient:
    """Stands in when no model is configured. Always abstains."""

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        return ""


class AnthropicClient:
    """First-party Claude API."""

    def __init__(self, model: str = DEFAULT_MODEL):
        import anthropic

        self._client = anthropic.Anthropic()
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in response.content if b.type == "text")


class BedrockClient:
    """Claude on Amazon Bedrock, so document text stays inside the tenant.

    Uses the Mantle client from the anthropic SDK rather than raw boto3
    InvokeModel — same messages surface as the first-party client.
    """

    def __init__(self, model: str = BEDROCK_MODEL, region: str = AWS_REGION):
        from anthropic import AnthropicBedrockMantle

        self._client = AnthropicBedrockMantle(aws_region=region)
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in response.content if b.type == "text")


class AgentUnavailable(RuntimeError):
    """Raised at startup so a misconfigured agent fails loudly, not silently."""


GEMINI_MODEL = os.environ.get("SDOC_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_ENDPOINT = os.environ.get(
    "SDOC_GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/models"
)


def _gemini_text(payload: dict) -> str:
    """Pull the reply text out of a generateContent response.

    Defensive on purpose: a blocked or empty candidate has no `parts`, and the
    resolver treats an empty string as an abstention rather than an error.
    """
    for candidate in payload.get("candidates") or []:
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if text:
            return text
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
        import urllib.request

        body = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
        }).encode("utf-8")

        request = urllib.request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": self._key},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return _gemini_text(json.loads(response.read()))


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
