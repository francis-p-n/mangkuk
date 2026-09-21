"""The classifier, held to labels rather than to its own confidence.

`eval/audit.py` measures how much of the corpus the rules will decide.
That is coverage, and coverage is not accuracy: broadening one invoice rule
until 55 berthing reports were filed as invoice questions left every test in
this suite green and *improved* the published residue figure.

These hold it to `eval/gold/clusters.json` - a human label for each of the 33
templates the corpus is written from - and to two invariants that need no
labels at all: emails written from one template must land in one category,
and the wording of a message must decide it.
"""
from __future__ import annotations

import sys

import pytest

from conftest import ROOT

sys.path.insert(0, str(ROOT / "eval"))

from classification import evaluate, read_gold        # noqa: E402
from fingerprint import fingerprint, load             # noqa: E402
from sdoc.classify import CATEGORIES, classify        # noqa: E402


@pytest.fixture(scope="module")
def scored():
    return evaluate()


@pytest.fixture(scope="module")
def clusters():
    return load()


class TestTheLabelsThemselves:
    def test_every_template_has_been_labelled(self, clusters):
        """A template nobody has decided about must not be skipped quietly."""
        gold = read_gold()
        missing = [c.id for c in clusters if c.id not in gold]
        assert not missing, (
            f"{len(missing)} template(s) with no label; run "
            f"eval/fingerprint.py and add them to eval/gold/clusters.json"
        )

    def test_every_label_is_a_real_category(self):
        for cid, row in read_gold().items():
            assert row["label"] in CATEGORIES, cid

    def test_every_label_names_the_exemplar_it_was_read_from(self, clusters):
        """The evidence for a judgement has to be checkable."""
        by_id = {c.id: c for c in clusters}
        for cid, row in read_gold().items():
            assert row.get("exemplar"), cid
            assert row.get("why"), cid
            ids = {e.email_id for e in by_id[cid].emails}
            assert row["exemplar"] in ids, (
                f"{cid} was labelled from {row['exemplar']}, which is no "
                f"longer in that template"
            )

    def test_no_template_mixes_two_kinds_of_email(self, clusters):
        """One label per template is only honest if the template is one thing."""
        impure = [c.id for c in clusters if not c.pure]
        assert not impure, impure

    def test_the_labels_cover_the_whole_corpus(self, scored):
        assert scored["strict"].total + scored["contested"].total == 520


class TestAccuracy:
    def test_the_classifier_agrees_with_every_plain_label(self, scored):
        wrong = scored["strict"].wrong
        assert not wrong, (
            f"{len(wrong)} disagreement(s), e.g. "
            f"{[(e, g, p) for e, g, p in wrong[:5]]}"
        )

    def test_macro_f1_is_perfect_on_the_plainly_labelled(self, scored):
        assert scored["strict"].macro_f1 == pytest.approx(1.0)

    def test_every_category_is_scored(self, scored):
        for cat in CATEGORIES:
            assert scored["strict"].per[cat]["support"] > 0, cat

    def test_the_contested_readings_are_argued_and_agreed_with(self, scored):
        """Two templates are judgement calls. They are scored apart from the
        headline so agreement there cannot flatter it - but the code and the
        argument in eval/gold/clusters.json still have to say the same thing."""
        assert not scored["contested"].wrong


class TestConsistency:
    """Needs no labels: one template is one message."""

    def test_no_template_is_split_across_categories(self, scored):
        split = scored["split"]
        assert not split, (
            f"{len(split)} template(s) land in more than one category: "
            f"{[(c['fingerprint'][:40], c['predicted']) for c in split.values()][:3]}"
        )


BODY_TEMPLATES = [
    ("Attached are the SI and draft BL for OC 5RSG-00133. Please check the "
     "details and confirm.", "BL_COMPARISON"),
    ("Please find Shipping instruction for 5RFR-37631. POL: SINGAPORE POD: "
     "GDANSK", "SI_REQUEST"),
    ("Query on invoice 5250075931: is the THC / local charge included?",
     "INVOICE_QUERY"),
    ("Kindly find the daily berthing report attached. Vessel MMSS 2507 "
     "berthed on schedule.", "GENERAL"),
]

# Every subject family in the corpus, including ones that used to drag a
# message into the wrong category on their own.
SUBJECTS = [
    "",
    "REQUEST SI _ 5RFR-37631 _ GDANSK_POLAND",
    "_Reminder_Paper - Submit SI & AED_10-01-2026",
    "Total Freight - INDIA - 5EFP-68392",
    "daily Berthing Report - 01 JAN 2026",
    "_Approval Required_ Time Off Request",
    "RE_ TO CONFIRM DOCS _ 5AAT-03056 _ AQABA_JORDAN",
    "2115 RAK BILLING 5070146244 MISSING GR",
]

BANNER = ("WARNING: This email originated outside of our organisation. As a "
          "security measure, do not click links.\n\n")
QUOTED = ("\n\n______________________________\nFrom: someone\n"
          "Sent: Tuesday\nOld thread text about an invoice and a berthing "
          "report\n")


class TestTheMessageDecides:
    """Metamorphic: changes that do not change what is being asked must not
    change the answer.

    The subject one is not a nicety. Subjects and bodies are drawn
    independently for operational mail in this corpus - email_075 is headed
    "Time Off Request" over an RPA billing notice - so a classifier that reads
    the heading over the message gives the same sentence two different
    answers, and which one you get is luck.
    """

    @pytest.mark.parametrize("body,expected", BODY_TEMPLATES)
    @pytest.mark.parametrize("subject", SUBJECTS)
    def test_the_subject_does_not_overrule_the_body(self, body, expected, subject):
        assert classify(subject, body, "aprilasia.com", []).category == expected

    @pytest.mark.parametrize("body,expected", BODY_TEMPLATES)
    def test_the_security_banner_changes_nothing(self, body, expected):
        assert classify("", BANNER + body, "aprilasia.com", []).category == expected

    @pytest.mark.parametrize("body,expected", BODY_TEMPLATES)
    def test_a_quoted_reply_underneath_changes_nothing(self, body, expected):
        assert classify("", body + QUOTED, "aprilasia.com", []).category == expected

    @pytest.mark.parametrize("body,expected", BODY_TEMPLATES)
    def test_shouting_changes_nothing(self, body, expected):
        assert classify("", body.upper(), "aprilasia.com", []).category == expected

    @pytest.mark.parametrize("body,expected", BODY_TEMPLATES)
    def test_reflowing_the_whitespace_changes_nothing(self, body, expected):
        reflowed = body.replace(" ", "\n  ")
        assert classify("", reflowed, "aprilasia.com", []).category == expected

    @pytest.mark.parametrize("body,expected", BODY_TEMPLATES)
    def test_another_shipment_is_the_same_kind_of_email(self, body, expected):
        """The reference is an identity, not a signal."""
        swapped = (body.replace("5RSG-00133", "7QTX-40118")
                       .replace("5RFR-37631", "7QTX-40118")
                       .replace("5250075931", "5250099999")
                       .replace("MMSS 2507", "SILVER KESTREL 442"))
        assert classify("", swapped, "aprilasia.com", []).category == expected


class TestTheFingerprintItself:
    """If the templates stop being recoverable, the labels stop meaning
    anything - so the thing the gold set is keyed on is pinned too."""

    def test_the_same_message_about_two_shipments_is_one_template(self):
        a = "Attached are the SI and draft BL for OC 5RSG-00133. Please check."
        b = "Attached are the SI and draft BL for OC 7QTX-40118. Please check."
        assert fingerprint("", a) == fingerprint("", b)

    def test_two_different_requests_are_two_templates(self):
        a = "Please assist to send the draft BL for SIN832764835 for checking."
        b = "Attached are the SI and draft BL for OC 5RSG-00133. Please check."
        assert fingerprint("", a) != fingerprint("", b)

    def test_the_signature_block_is_not_part_of_the_message(self):
        body = "Query on invoice 5250075931: is the THC included?"
        signed = body + ("\n\nBest Regards,\nWilly Situmorang\nShipping "
                         "Documentation\nDID : +971 04 4938289\n")
        assert fingerprint("", body) == fingerprint("", signed)

    def test_an_email_with_no_body_is_keyed_on_its_subject(self):
        assert fingerprint("Your account needs verifying", "  \n ").startswith(
            "SUBJECT:")
