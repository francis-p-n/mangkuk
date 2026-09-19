"""The agentic layer — and the leash it runs on.

The pipeline is a cascade, cheapest and most certain first:

    1. labelled parse   deterministic, colon-anchored
    2. block parse      deterministic, label-above-value
    3. resolver agent   an LLM, but only for what 1 and 2 left missing
    4. escalation       a person, only when 3 declines or cannot be trusted

Stage 3 is the only place a model touches a shipment field, and it is never
believed on its word. It must return a verbatim quote from the document, that
quote must actually appear in the document, and the value must appear inside
the quote. A model that invents a consignee fails all three checks and is
discarded — the field stays missing and the email escalates, exactly as if the
agent had never run.

This is the point of the design: the agent can only ever *find* a value that is
already in the document. It cannot author one. Whatever it finds still goes
through the same deterministic comparator as everything else.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field as dc_field
from typing import Protocol

from .classify import CATEGORIES
from .fields import FIELDS, Extracted, FieldSet, plausible

DEFAULT_MODEL = os.environ.get("SDOC_MODEL", "claude-opus-5")
BEDROCK_MODEL = os.environ.get("SDOC_BEDROCK_MODEL", "anthropic.claude-opus-5")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_WS = re.compile(r"\s+")


def _squash(text: str) -> str:
    """Whitespace-insensitive form, so a quote still matches across line wraps."""
    return _WS.sub(" ", text).strip().lower()


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


def make_client(provider: str) -> LLMClient:
    """Build a client, or explain clearly why it cannot be built.

    Failing at startup is deliberate. A silent fallback to NullClient would
    look like a clean run in which the agent simply found nothing.
    """
    if provider == "off":
        return NullClient()
    try:
        return BedrockClient() if provider == "bedrock" else AnthropicClient()
    except ImportError as exc:
        raise AgentUnavailable(
            "the anthropic SDK is not installed - run: pip install anthropic"
        ) from exc
    except Exception as exc:
        hint = (
            "check AWS credentials and AWS_REGION, and that the model is enabled "
            f"in Bedrock ({BEDROCK_MODEL})"
            if provider == "bedrock"
            else "check ANTHROPIC_API_KEY"
        )
        raise AgentUnavailable(f"{type(exc).__name__}: {exc} - {hint}") from exc


@dataclass
class AgentStats:
    resolver_calls: int = 0
    fields_requested: int = 0
    fields_returned: int = 0
    fields_accepted: int = 0
    rejected_ungrounded: int = 0
    rejected_implausible: int = 0
    triage_calls: int = 0
    triage_accepted: int = 0
    notes: list[str] = dc_field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "notes"}


def _parse_json_object(raw: str) -> dict:
    """Models sometimes wrap JSON in prose or a code fence. Take the object."""
    if not raw or not raw.strip():
        return {}
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


RESOLVER_SYSTEM = """You locate values in shipping documents. You never invent them.

You are given the full text of one shipping document and a list of fields that
a deterministic parser could not find. For each field, find the value in the
document if — and only if — it is genuinely present.

Return a JSON object, nothing else:

{"<field>": {"value": "<the value exactly as written>",
             "quote": "<the verbatim line or lines from the document containing it>"}}

Rules that matter more than being helpful:
- The quote must be copied character-for-character from the document.
- The value must appear inside the quote.
- If a field is not in the document, omit it. Do not guess, infer from context,
  or carry a value over from a similar field.
- An omitted field is a correct answer. A plausible-looking invention is not:
  it would put the wrong consignee on a bill of lading.

Field meanings:
- shipper: the exporting party
- consignee: the receiving party (may be labelled "to the order of")
- notify_party: the party to notify on arrival
- port_of_loading: origin port
- port_of_discharge: destination port
- container_count: number and type of containers, e.g. "6 x 40'HC"
- gross_weight_kg: total gross weight in kilograms"""


class FieldResolver:
    """Stage 3. Finds missing fields, and is disbelieved by default."""

    def __init__(self, client: LLMClient, stats: AgentStats | None = None):
        self.client = client
        self.stats = stats or AgentStats()

    def resolve(self, text: str, fields: FieldSet, doc_role: str = "") -> int:
        """Fill missing fields in place. Returns how many were accepted."""
        missing = fields.missing
        if not missing or isinstance(self.client, NullClient) or not text.strip():
            return 0

        self.stats.resolver_calls += 1
        self.stats.fields_requested += len(missing)

        user = (
            f"Document ({doc_role or 'unknown type'}):\n"
            f"---\n{text}\n---\n\n"
            f"Fields not found by the parser: {', '.join(missing)}\n\n"
            "Return the JSON object described in your instructions."
        )
        try:
            raw = self.client.complete(RESOLVER_SYSTEM, user)
        except Exception as exc:
            self.stats.notes.append(f"resolver call failed: {type(exc).__name__}")
            return 0

        proposals = _parse_json_object(raw)
        haystack = _squash(text)
        accepted = 0

        for name, payload in proposals.items():
            if name not in FIELDS or name in fields.values:
                continue
            if not isinstance(payload, dict):
                continue
            value = str(payload.get("value", "")).strip()
            quote = str(payload.get("quote", "")).strip()
            if not value or not quote:
                continue

            self.stats.fields_returned += 1

            # Grounding: the quote must exist in the document, and the value
            # must be inside the quote. Either failing means the model wrote
            # something the document does not say.
            if _squash(quote) not in haystack or _squash(value) not in _squash(quote):
                self.stats.rejected_ungrounded += 1
                continue
            if not plausible(name, value):
                self.stats.rejected_implausible += 1
                continue

            line_no = _line_of(text, quote)
            fields.values[name] = Extracted(
                value=value,
                label=f"resolved by agent ({doc_role or 'document'})",
                line_no=line_no,
                raw_line=quote.splitlines()[0] if quote else "",
                detail="",
            )
            accepted += 1

        self.stats.fields_accepted += accepted
        return accepted


def _line_of(text: str, quote: str) -> int:
    """1-indexed line where the quote starts, 0 if it cannot be placed."""
    head = _squash(quote.splitlines()[0]) if quote.splitlines() else ""
    if not head:
        return 0
    for i, line in enumerate(text.splitlines(), start=1):
        if head and head in _squash(line):
            return i
    return 0


TRIAGE_SYSTEM = f"""You categorise emails arriving at a shipping documentation desk.

Reply with a JSON object and nothing else: {{"category": "<one of {', '.join(CATEGORIES)}>"}}

- BL_COMPARISON: asks for a draft bill of lading to be checked against a
  shipping instruction, or encloses both for checking.
- SI_REQUEST: concerns preparing, requesting or submitting a shipping instruction.
- INVOICE_QUERY: concerns an invoice, freight charges, local charges or billing.
- GENERAL: operational traffic — vessel updates, berthing reports, planning,
  reminders, internal notices.
- SPAM: unsolicited commercial mail, phishing, prize or delivery-fee scams.

Choose GENERAL when nothing else clearly fits."""


class TriageAgent:
    """Stage 3 for classification — only sees what the rules abstained on."""

    def __init__(self, client: LLMClient, stats: AgentStats | None = None):
        self.client = client
        self.stats = stats or AgentStats()

    def classify(self, subject: str, body: str) -> str | None:
        if isinstance(self.client, NullClient):
            return None
        self.stats.triage_calls += 1
        user = f"Subject: {subject}\n\nBody:\n{body[:2500]}"
        try:
            raw = self.client.complete(TRIAGE_SYSTEM, user, max_tokens=256)
        except Exception as exc:
            self.stats.notes.append(f"triage call failed: {type(exc).__name__}")
            return None

        category = str(_parse_json_object(raw).get("category", "")).strip().upper()
        if category in CATEGORIES:
            self.stats.triage_accepted += 1
            return category
        return None
