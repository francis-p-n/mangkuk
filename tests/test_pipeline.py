"""End-to-end run over the real bundle, plus a pinned regression set.

The regression cases below were each verified by reading the two source
documents by hand. They are the guard against a normalization change quietly
breaking a defect we already catch.
"""
import json

import pytest

from sdoc.mailsource import BundleMailSource
from sdoc.pipeline import run
from sdoc.validate import validate


@pytest.fixture(scope="module")
def results():
    return {r.email_id: r for r in run(BundleMailSource("data"))}


class TestWholeInbox:
    def test_every_email_is_answered(self, results):
        assert len(results) == 520

    def test_submission_is_valid(self, results):
        sub = {eid: r.to_submission() for eid, r in results.items()}
        assert validate(sub, "data/sample_submission.json") == []

    def test_all_five_categories_are_used(self, results):
        assert {r.category for r in results.values()} == {
            "BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"
        }

    def test_non_comparison_emails_carry_no_verdict(self, results):
        for r in results.values():
            if r.category != "BL_COMPARISON":
                assert (r.status, r.review_reason, r.has_defect, r.defect_fields) == \
                    ("OK", None, False, [])

    def test_every_decided_comparison_examined_all_seven_fields(self, results):
        decided = [r for r in results.values()
                   if r.category == "BL_COMPARISON" and r.status in ("OK", "MISMATCH")]
        assert decided
        assert all(len(r.comparisons) == 7 for r in decided)

    def test_every_defect_has_both_values_as_evidence(self, results):
        for r in results.values():
            for c in r.comparisons:
                if c["agree"] is False:
                    assert c["si_value"] and c["bl_value"]
                    assert c["si_label"] and c["bl_label"]

    def test_unextractable_documents_are_never_silently_decided(self, results):
        for r in results.values():
            unreadable = [d for d in r.documents if d.get("present") and not d.get("readable")]
            if unreadable:
                assert r.status == "NEEDS_REVIEW" and r.review_reason == "unreadable"


class TestPinnedCases:
    @pytest.mark.parametrize("eid,fields", [
        ("email_004", ["consignee", "notify_party"]),   # BL says 'To the Order of'
        ("email_013", ["port_of_discharge"]),           # same locode, different port
        ("email_031", ["container_count", "gross_weight_kg"]),
        ("email_043", ["container_count"]),
        ("email_046", ["notify_party"]),
        ("email_065", ["notify_party", "port_of_discharge"]),
        ("email_071", ["port_of_discharge", "container_count"]),
    ])
    def test_known_defects(self, results, eid, fields):
        r = results[eid]
        assert r.status == "MISMATCH" and r.has_defect
        assert sorted(r.defect_fields) == sorted(fields)

    @pytest.mark.parametrize("eid", ["email_001", "email_009", "email_032"])
    def test_known_clean_drafts(self, results, eid):
        assert results[eid].status == "OK"

    def test_pdf_pair_is_read_from_a_block_layout(self, results):
        # Labels sit on their own line with the value underneath, and the
        # container table must not be mistaken for the weight total.
        r = results["email_059"]
        assert r.status == "OK"
        by_field = {c["field"]: c for c in r.comparisons}
        assert by_field["gross_weight_kg"]["si_value"] == "131,322 KG"
        assert by_field["consignee"]["bl_label"] == "Consignee (Non-Negotiable)"

    @pytest.mark.parametrize("eid,fields", [
        ("email_313", ["container_count", "gross_weight_kg"]),
        ("email_434", ["port_of_discharge"]),
    ])
    def test_defects_found_inside_pdfs(self, results, eid, fields):
        assert sorted(results[eid].defect_fields) == sorted(fields)

    @pytest.mark.parametrize("eid,reason", [
        ("email_501", "wrong_doc_type"),
        ("email_502", "wrong_doc_type"),
        ("email_507", "missing_attachment"),
        ("email_509", "missing_attachment"),
        ("email_516", "missing_value"),
        ("email_519", "missing_value"),
        ("email_520", "missing_value"),
        ("email_513", "unreadable"),   # PDF with no extractable text
    ])
    def test_known_escalations(self, results, eid, reason):
        r = results[eid]
        assert r.status == "NEEDS_REVIEW" and r.review_reason == reason

    def test_the_alias_trap_resolves_correctly(self, results):
        c = {x["field"]: x for x in results["email_004"].comparisons}["consignee"]
        assert c["si_label"] == "Consignee (Non-Negotiable)"
        assert c["bl_label"] == "To the Order of"

    def test_shipment_reference_is_threaded(self, results):
        assert results["email_001"].oc_number == "5RSG-00133"
        assert results["email_004"].oc_number == "5ALT-01226"
