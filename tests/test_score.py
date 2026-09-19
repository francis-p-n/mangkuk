"""The scorer has to be right before its numbers mean anything.

Ground truth arrives from the organizers; this suite proves that when it does,
the report tells the truth about our own output. Each test injects a known
error and checks the scorer finds exactly that.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from score import (  # noqa: E402
    defect_field_f1, end_to_end, macro_f1_categories, review_axis,
)


def rec(category="BL_COMPARISON", status="OK", reason=None, fields=None):
    return {"category": category, "status": status, "review_reason": reason,
            "defect_fields": fields or [], "has_defect": status == "MISMATCH"}


@pytest.fixture
def truth():
    return {
        "e1": rec(status="MISMATCH", fields=["consignee"]),
        "e2": rec(status="MISMATCH", fields=["container_count", "gross_weight_kg"]),
        "e3": rec(status="OK"),
        "e4": rec(status="OK"),
        "e5": rec(status="NEEDS_REVIEW", reason="unreadable"),
        "e6": rec(category="SPAM"),
        "e7": rec(category="GENERAL"),
        "e8": rec(category="SI_REQUEST"),
    }


@pytest.fixture
def ids(truth):
    return sorted(truth)


class TestPerfectSubmission:
    def test_scores_everything_at_one(self, truth, ids):
        macro, _ = macro_f1_categories(truth, truth, ids)
        micro, macro_def, _ = defect_field_f1(truth, truth, ids)
        e2e = end_to_end(truth, truth, ids)
        assert macro == pytest.approx(1.0)
        assert micro == pytest.approx(1.0) and macro_def == pytest.approx(1.0)
        assert e2e["rate"] == pytest.approx(1.0) and e2e["false_alarms"] == 0
        assert review_axis(truth, truth, ids)["f1"] == pytest.approx(1.0)


class TestEndToEnd:
    def test_a_missed_defect_is_counted(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e1"] = rec(status="OK")
        e2e = end_to_end(truth, sub, ids)
        assert e2e["defective"] == 2 and e2e["caught"] == 1
        assert e2e["lost_at_compare"] == 1 and e2e["lost_at_classify"] == 0

    def test_a_defect_lost_by_misclassification_is_attributed_correctly(self, truth, ids):
        # Caught nothing because the email never reached the comparison stage.
        sub = copy.deepcopy(truth)
        sub["e1"] = rec(category="GENERAL", status="OK")
        e2e = end_to_end(truth, sub, ids)
        assert e2e["lost_at_classify"] == 1 and e2e["lost_at_compare"] == 0

    def test_right_verdict_wrong_fields_still_counts_as_caught(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e2"] = rec(status="MISMATCH", fields=["shipper"])
        e2e = end_to_end(truth, sub, ids)
        assert e2e["caught"] == 2 and e2e["exact_fields"] == 1

    def test_false_alarms_are_counted_against_clean_drafts(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e3"] = rec(status="MISMATCH", fields=["shipper"])
        e2e = end_to_end(truth, sub, ids)
        assert e2e["false_alarms"] == 1 and e2e["clean"] == 2


class TestCategoryF1:
    def test_a_flip_lowers_macro_f1(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e7"] = rec(category="SPAM")
        macro, per = macro_f1_categories(truth, sub, ids)
        assert macro < 1.0
        assert per["GENERAL"]["recall"] == pytest.approx(0.0)
        assert per["SPAM"]["precision"] == pytest.approx(0.5)

    def test_absent_categories_do_not_drag_the_average(self, truth, ids):
        # INVOICE_QUERY has no support here and must not count as a zero.
        macro, per = macro_f1_categories(truth, truth, ids)
        assert per["INVOICE_QUERY"]["support"] == 0
        assert macro == pytest.approx(1.0)


class TestDefectFieldF1:
    def test_a_missing_field_costs_recall(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e2"] = rec(status="MISMATCH", fields=["container_count"])
        _, _, per = defect_field_f1(truth, sub, ids)
        assert per["gross_weight_kg"]["fn"] == 1
        assert per["gross_weight_kg"]["recall"] == pytest.approx(0.0)

    def test_an_extra_field_costs_precision(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e1"] = rec(status="MISMATCH", fields=["consignee", "shipper"])
        _, _, per = defect_field_f1(truth, sub, ids)
        assert per["shipper"]["fp"] == 1
        assert per["consignee"]["f1"] == pytest.approx(1.0)


class TestReviewAxis:
    def test_agreement_on_status_but_not_reason_is_visible(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e5"] = rec(status="NEEDS_REVIEW", reason="missing_value")
        rev = review_axis(truth, sub, ids)
        assert rev["agreed"] == 1 and rev["reason_match"] == 0

    def test_over_escalation_costs_precision(self, truth, ids):
        sub = copy.deepcopy(truth)
        sub["e3"] = rec(status="NEEDS_REVIEW", reason="unreadable")
        rev = review_axis(truth, sub, ids)
        assert rev["reported"] == 2 and rev["precision"] == pytest.approx(0.5)
