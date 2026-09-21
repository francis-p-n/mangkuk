"""What the triage agent says about its own certainty, and whether to believe it.

A model asked how sure it is will generally say "quite". So the number it
reports is paired with a check it cannot talk its way past: the phrase it
claims decided the category has to appear in the email. A quotation that is
not there caps the number beside it, whatever the number said.

This is the signal a cascade escalates on, so it has to be wrong in the safe
direction: an unreadable reply is uncertain, not certain.
"""
from __future__ import annotations

import json

import pytest

from sdoc.agents.stats import AgentStats
from sdoc.agents.triage import TriageAgent, UNGROUNDED_CEILING, _confidence


class FakeClient:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, max_tokens=1024):
        return self.reply


def triage(category="INVOICE_QUERY", confidence=0.9, because="invoice 5250072"):
    body = {"category": category}
    if confidence is not None:
        body["confidence"] = confidence
    if because is not None:
        body["because"] = because
    stats = AgentStats()
    agent = TriageAgent(FakeClient(json.dumps(body)), stats)
    got = agent.classify(
        "Payment for invoice 5250072",
        "Please arrange payment for invoice 5250072 at your convenience.",
    )
    return got, stats


class TestReadingTheNumber:
    @pytest.mark.parametrize("raw,want", [
        (0.9, 0.9),
        ("0.35", 0.35),
        (0, 0.0),
        (1, 1.0),
    ])
    def test_a_probability_is_taken_as_written(self, raw, want):
        assert _confidence(raw) == want

    @pytest.mark.parametrize("raw,want", [(85, 0.85), (100, 1.0), (2, 0.02)])
    def test_a_percentage_is_divided(self, raw, want):
        assert _confidence(raw) == pytest.approx(want)

    @pytest.mark.parametrize("raw", [1.7, 250, 1.0001])
    def test_an_over_range_value_means_certain(self, raw):
        """Reading 1.7 as a percentage would turn the most confident answer
        into the least, which is the one direction this must not get wrong."""
        assert _confidence(raw) == 1.0

    @pytest.mark.parametrize("raw", ["high", "", None, {}, float("nan")])
    def test_an_unreadable_answer_is_neither_sure_nor_unsure(self, raw):
        got = _confidence(raw)
        assert got == 0.5

    def test_a_negative_number_is_no_confidence(self):
        assert _confidence(-2) == 0.0


class TestGrounding:
    def test_a_quoted_phrase_that_is_in_the_email_is_believed(self):
        _, stats = triage(because="invoice 5250072", confidence=0.9)
        assert stats.triage_confidence == [0.9]
        assert stats.triage_ungrounded == 0

    def test_a_phrase_that_is_not_in_the_email_caps_the_number(self):
        _, stats = triage(because="as agreed on the telephone", confidence=0.95)
        assert stats.triage_confidence == [UNGROUNDED_CEILING]
        assert stats.triage_ungrounded == 1

    def test_the_category_still_stands(self):
        """An unsupported reason is a reason to look again, not to discard."""
        got, _ = triage(because="nowhere in this email", confidence=0.95)
        assert got == "INVOICE_QUERY"

    def test_case_and_spacing_do_not_break_the_match(self):
        _, stats = triage(because="INVOICE   5250072", confidence=0.8)
        assert stats.triage_ungrounded == 0

    def test_no_reason_offered_is_not_punished(self):
        """Nothing was claimed, so there is nothing to disbelieve."""
        _, stats = triage(because=None, confidence=0.8)
        assert stats.triage_confidence == [0.8]
        assert stats.triage_ungrounded == 0


class TestWhatGetsRecorded:
    def test_every_call_leaves_a_number(self):
        _, stats = triage(confidence=None)
        assert len(stats.triage_confidence) == 1
        assert stats.triage_confidence[0] == 0.5

    def test_a_reply_with_no_category_is_still_measured(self):
        stats = AgentStats()
        agent = TriageAgent(FakeClient('{"confidence": 0.2}'), stats)
        assert agent.classify("x", "y") is None
        assert stats.triage_confidence == [0.2]
