"""The agentic layer, and the leash it runs on.

The pipeline is a cascade, cheapest and most certain first:

    1. labelled parse   deterministic, colon-anchored
    2. block parse      deterministic, label-above-value
    3. resolver agent   an LLM, but only for what 1 and 2 left missing
    4. escalation       a person, only when 3 declines or cannot be trusted

Stage 3 is the only place a model touches a shipment field, and it is never
believed on its word.

    clients.py   one class per provider, behind a single method
    prompts.py   what each agent is told
    replies.py   reading a model's reply defensively
    resolver.py  finding missing fields, and disbelieving the answer
    triage.py    classifying what the rules abstained on
    stats.py     what the stage did, counted
"""
from __future__ import annotations

from .clients import (
    AWS_REGION, BEDROCK_MODEL, DEFAULT_MODEL, GEMINI_ENDPOINT, GEMINI_MODEL,
    MAX_RETRIES, AgentUnavailable, AnthropicClient, BedrockClient,
    BudgetExhausted, GeminiClient, LLMClient, NullClient, RateLimited,
    _gemini_text, _retry_after, limiter, make_client, reset_limiter,
)
from .limiter import Limiter
from .prompts import RESOLVER_SYSTEM, TRIAGE_SYSTEM
from .replies import _parse_json_object, _squash
from .resolver import FieldResolver
from .stats import AgentStats
from .triage import TriageAgent

__all__ = [
    "LLMClient", "NullClient", "AnthropicClient", "BedrockClient", "GeminiClient",
    "make_client", "AgentUnavailable", "RateLimited", "reset_limiter", "limiter", "Limiter", "BudgetExhausted", "MAX_RETRIES",
    "FieldResolver", "TriageAgent", "AgentStats",
    "RESOLVER_SYSTEM", "TRIAGE_SYSTEM",
    "DEFAULT_MODEL", "BEDROCK_MODEL", "GEMINI_MODEL", "GEMINI_ENDPOINT", "AWS_REGION",
]
