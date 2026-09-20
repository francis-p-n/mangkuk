"""Stage-1 classification for whatever the rules abstained on."""
from __future__ import annotations

from ..classify import CATEGORIES
from .clients import NullClient, RateLimited
from .prompts import TRIAGE_SYSTEM
from .replies import _parse_json_object
from .stats import AgentStats


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
        except RateLimited as exc:
            # Never answered. The email falls back to the rule's own verdict,
            # exactly as if the agent were off, but the run has to know this
            # was silence rather than a shrug.
            self.stats.rate_limited += 1
            self.stats.notes.append(f"triage: {exc}")
            self.stats.say("rate limited")
            return None
        except Exception as exc:
            self.stats.failed += 1
            self.stats.notes.append(f"triage call failed: {type(exc).__name__}")
            self.stats.say(f"failed ({type(exc).__name__})")
            return None

        category = str(_parse_json_object(raw).get("category", "")).strip().upper()
        if category in CATEGORIES:
            self.stats.triage_accepted += 1
            self.stats.say(f"classified as {category}")
            return category
        self.stats.say("abstained")
        return None
