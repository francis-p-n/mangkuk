"""Stage-1 classification for whatever the rules abstained on."""
from __future__ import annotations

from ..classify import CATEGORIES
from .clients import BudgetExhausted, NullClient, RateLimited
from .prompts import TRIAGE_SYSTEM
from .replies import _parse_json_object, _squash
from .stats import AgentStats


# What a claimed reason that is not in the email does to the number beside
# it. Not zero: the category may still be right, and the reply is still an
# opinion worth having. It simply stops being one worth trusting without a
# second look, which is exactly what the cascade threshold is for.
UNGROUNDED_CEILING = 0.4


def _confidence(raw) -> float:
    """A number in [0, 1], however the model chose to express it.

    Anything unreadable becomes 0.5 rather than 0 or 1: a reply that did not
    answer the question is not evidence of certainty in either direction.
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.5

    # NaN compares false against everything, so min() and max() hand it
    # straight back and a clamp that looks total lets it through as 1.0 -
    # an unreadable answer arriving as maximum confidence, which would
    # escalate nothing and be believed completely.
    if v != v:
        return 0.5

    # A model asked for 0-1 sometimes answers in percent. Two is the dividing
    # line: nobody reports 1.7% confidence, so a value just over one is an
    # over-range probability and means "certain", while 85 means 85%. Reading
    # 1.7 as a percentage would turn the most confident possible answer into
    # the least, which is the one direction this must never get wrong.
    if 2.0 <= v <= 100.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


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
        except BudgetExhausted as exc:
            # Not a failure and not throttling: the run chose to stop asking.
            # Counted with the rate limited, because the outcome is the same -
            # no answer, so the email falls back to the rules - but the note
            # says which it was, since only one of them is worth waiting out.
            self.stats.rate_limited += 1
            self.stats.notes.append(f"triage: {exc}")
            self.stats.say("budget spent")
            return None
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

        reply = _parse_json_object(raw)
        category = str(reply.get("category", "")).strip().upper()

        # How sure it says it is, and whether the email bears that out.
        #
        # Self-reported confidence on its own is worth very little - a model
        # asked how sure it is will generally say "quite" - so it is paired
        # with a check the model cannot talk its way past: the phrase it
        # claims decided the category has to actually appear in the email.
        # A quotation that is not there is a reason to disbelieve the number
        # attached to it, whatever the number says.
        confidence = _confidence(reply.get("confidence"))
        because = str(reply.get("because", "")).strip()
        haystack = _squash(subject + " " + body)
        grounded = bool(because) and _squash(because) in haystack
        if because and not grounded:
            confidence = min(confidence, UNGROUNDED_CEILING)
            self.stats.triage_ungrounded += 1

        self.stats.triage_confidence.append(confidence)
        if category in CATEGORIES:
            self.stats.triage_accepted += 1
            self.stats.say(f"classified as {category}")
            return category
        self.stats.say("abstained")
        return None
