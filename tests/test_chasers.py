"""The evidence behind the draft-chaser decision, pinned.

91 emails ask a counterparty to *send* a draft BL and carry no attachment.
Filing them as GENERAL rather than BL_COMPARISON/missing_attachment is the
single largest classification call in the corpus, and Stage 1 is scored by
macro-F1, so getting it wrong damages two categories at once.

docs/assumptions.md argues the call from four corpus facts. These tests assert
those facts directly, so the argument cannot quietly stop being true — if the
corpus is swapped for the organizers' hidden set and the wording no longer
separates, this fails loudly instead of silently misfiling 91 emails.
"""
from __future__ import annotations

import json
import re

import pytest

from sdoc.classify import classify

CHASE_PHRASES = ("assist to send the draft bl", "send the draft bl for")

# The three hand-built missing_attachment cases that carry no attachment at
# all, which is what makes them structurally indistinguishable from a chaser.
CONSTRUCTED_EMPTY = ("email_506", "email_508", "email_510")

OC = re.compile(r"\b\d[A-Z]{3}-\d{5}\b")
BODY_REF = re.compile(r"send the draft BL for ([A-Z0-9]+) for checking", re.I)
BOOKING = re.compile(r"\b(?:SIN|MCLSIN|PSGSE|EGLV|MCLSINJEA)[A-Z0-9]{6,}\b")


@pytest.fixture(scope="module")
def corpus(data_dir) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((data_dir / "inbox").glob("*.json"))]


def is_chaser(email: dict) -> bool:
    return any(p in email["body"].lower() for p in CHASE_PHRASES)


def has_shipping_docs(email: dict) -> bool:
    return any("_SI." in a or "_BL." in a for a in email["attachments"])


@pytest.fixture(scope="module")
def chasers(corpus) -> list[dict]:
    return [e for e in corpus if is_chaser(e)]


class TestTheChasersThemselves:
    def test_there_are_ninety_one(self, chasers):
        assert len(chasers) == 91

    def test_none_carry_an_attachment(self, chasers):
        assert [e["email_id"] for e in chasers if e["attachments"]] == []

    def test_they_are_a_single_template(self, chasers):
        shapes = {re.sub(r"[A-Z0-9]{6,}", "#", line.strip())
                  for e in chasers for line in e["body"].split("\n")
                  if "draft bl" in line.lower()}
        assert shapes == {"Please assist to send the draft BL for # for checking asap."}


class TestWordingSeparatesThemCompletely:
    """The discriminator is what the sender asks for, not what they attached."""

    def test_no_chaser_asks_for_a_comparison(self, chasers):
        assert not [e["email_id"] for e in chasers if "compare" in e["body"].lower()]

    def test_no_chaser_mentions_a_lost_attachment(self, chasers):
        assert not [e["email_id"] for e in chasers
                    if any(w in e["body"].lower()
                           for w in ("attached", "dropped", "missing"))]

    def test_the_constructed_cases_are_also_attachment_free(self, corpus):
        built = [e for e in corpus if e["email_id"] in CONSTRUCTED_EMPTY]
        assert len(built) == 3
        assert all(e["attachments"] == [] for e in built)

    def test_but_every_constructed_case_asks_to_compare(self, corpus):
        built = [e for e in corpus if e["email_id"] in CONSTRUCTED_EMPTY]
        assert all("compare" in e["body"].lower() for e in built)
        assert not any("send the draft" in e["body"].lower() for e in built)


class TestTheChaserReferenceIsFiller:
    """A chaser names a booking reference that leads nowhere."""

    def test_body_reference_never_matches_its_own_subject(self, chasers):
        agree = disagree = 0
        for e in chasers:
            found = BODY_REF.search(e["body"])
            subject_refs = set(BOOKING.findall(e["subject"]))
            if not found or not subject_refs:
                continue
            if found.group(1) in subject_refs:
                agree += 1
            else:
                disagree += 1
        assert disagree == 33, "the corpus shape changed - re-read assumptions.md"
        assert agree == 0

    def test_body_reference_appears_nowhere_else(self, corpus, chasers, data_dir):
        everything = " ".join(e["subject"] + " " + e["body"] for e in corpus)
        attachments = " ".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in (data_dir / "attachments").glob("*.txt"))
        for e in chasers:
            found = BODY_REF.search(e["body"])
            assert found, e["email_id"]
            ref = found.group(1)
            assert everything.count(ref) == 1, f"{e['email_id']}: {ref} recurs"
            assert ref not in attachments, f"{e['email_id']}: {ref} is in a document"

    def test_no_chaser_shipment_is_ever_actually_checked(self, corpus, chasers):
        def oc_numbers(emails):
            return {m for e in emails for m in OC.findall(e["subject"] + " " + e["body"])}

        chased = oc_numbers(chasers)
        checked = oc_numbers([e for e in corpus if has_shipping_docs(e)])
        assert len(chased) == 78 and len(checked) == 116
        assert chased & checked == set()


class TestTheCorpusConventionForAttachmentLessMail:
    """SI_REQUEST is the precedent: a named document, nothing attached, and
    its own workflow category rather than a broken comparison."""

    def test_every_si_request_carries_no_attachment(self, corpus):
        si = [e for e in corpus
              if classify(e["subject"], e["body"], e["from"].split("@")[-1],
                          e["attachments"]).category == "SI_REQUEST"]
        # 141 until the subject stopped outranking the body. Nine of those
        # were berthing reports and loading updates wearing a "Submit SI &
        # AED" heading the generator had stapled on; they are GENERAL now,
        # and eval/classification.py holds the whole corpus to that reading.
        assert len(si) == 132
        assert all(e["attachments"] == [] for e in si)


class TestRouting:
    def test_chasers_are_general_by_default(self, chasers):
        assert {classify(e["subject"], e["body"], e["from"].split("@")[-1],
                         e["attachments"]).category for e in chasers} == {"GENERAL"}

    def test_constructed_cases_reach_the_comparison_stage(self, corpus):
        for e in (e for e in corpus if e["email_id"] in CONSTRUCTED_EMPTY):
            got = classify(e["subject"], e["body"], e["from"].split("@")[-1],
                           e["attachments"])
            assert got.category == "BL_COMPARISON", e["email_id"]

    def test_the_flag_moves_the_chasers_and_nothing_else(self, corpus, chasers):
        def tally(flag):
            return sum(classify(e["subject"], e["body"], e["from"].split("@")[-1],
                                e["attachments"], flag).category == "BL_COMPARISON"
                       for e in corpus)

        assert tally(False) == 129
        assert tally(True) == 129 + len(chasers) == 220
