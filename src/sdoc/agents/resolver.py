"""The recovery stage, and the leash it runs on.

The model may only *find* a value already written in the document. Every
proposal must come back with a verbatim quote, that quote must appear in the
document, the value must appear inside the quote, and typed fields must still
parse. A proposal failing any check is discarded and the field stays missing,
so the email escalates exactly as if the agent had never run.
"""
from __future__ import annotations

from ..fields import FIELDS, Extracted, FieldSet, is_placeholder, plausible
from .clients import NullClient, RateLimited
from .prompts import RESOLVER_SYSTEM
from .replies import _parse_json_object, _squash
from .stats import AgentStats


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
        except RateLimited as exc:
            # The fields stay missing and the email escalates, which is the
            # same outcome as the agent being off - but it is silence, not a
            # judgement, and the run says so at the end.
            self.stats.rate_limited += 1
            self.stats.notes.append(f"resolver: {exc}")
            self.stats.say("rate limited")
            return 0
        except Exception as exc:
            self.stats.failed += 1
            self.stats.notes.append(f"resolver call failed: {type(exc).__name__}")
            self.stats.say(f"failed ({type(exc).__name__})")
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
            # An unfilled blank is grounded - "____MT" and "TBA" really are
            # printed on the instruction - so grounding alone waves it through
            # and the comparison then reports the carrier's real port as a
            # discrepancy against it. That is the false alarm the reading pass
            # already refuses to raise (fields/placeholders.py), and the agent
            # must not be the way back in: it would send a clerk to argue with
            # a carrier about a field their own side never filled in.
            if is_placeholder(value):
                self.stats.rejected_placeholder += 1
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
        self.stats.say(f"{accepted} of {len(missing)} field(s) accepted"
                       f" from the {doc_role or 'document'}")
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
