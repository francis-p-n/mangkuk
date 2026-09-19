import json

import pytest

from sdoc.validate import validate

SAMPLE = "data/sample_submission.json"


def ok_record(**over):
    rec = {"category": "GENERAL", "status": "OK", "review_reason": None,
           "defect_fields": [], "has_defect": False}
    rec.update(over)
    return rec


@pytest.fixture(scope="module")
def ids():
    return list(json.loads(open(SAMPLE, encoding="utf-8").read()))


def full(ids, **override_first):
    sub = {eid: ok_record() for eid in ids}
    if override_first:
        sub[ids[0]] = ok_record(**override_first)
    return sub


class TestShape:
    def test_a_clean_submission_passes(self, ids):
        assert validate(full(ids), SAMPLE) == []

    def test_missing_ids_are_reported(self, ids):
        sub = full(ids)
        sub.pop(ids[0])
        assert any("missing" in p for p in validate(sub, SAMPLE))

    def test_unknown_ids_are_reported(self, ids):
        sub = full(ids)
        sub["email_999999"] = ok_record()
        assert any("unexpected" in p for p in validate(sub, SAMPLE))

    def test_extra_key_in_a_record_is_reported(self, ids):
        sub = full(ids)
        sub[ids[0]] = ok_record() | {"confidence": 0.9}
        assert any("differ from the sample" in p for p in validate(sub, SAMPLE))


class TestConsistency:
    def test_has_defect_must_track_status(self, ids):
        problems = validate(full(ids, has_defect=True), SAMPLE)
        assert any("contradicts" in p for p in problems)

    def test_mismatch_needs_defect_fields(self, ids):
        problems = validate(full(ids, status="MISMATCH", has_defect=True), SAMPLE)
        assert any("no defect_fields" in p for p in problems)

    def test_review_reason_only_on_needs_review(self, ids):
        problems = validate(full(ids, review_reason="unreadable"), SAMPLE)
        assert any("iff status is NEEDS_REVIEW" in p for p in problems)

    def test_enums_are_checked(self, ids):
        problems = validate(full(ids, category="URGENT"), SAMPLE)
        assert any("bad category" in p for p in problems)

    def test_a_well_formed_mismatch_passes(self, ids):
        sub = full(ids, category="BL_COMPARISON", status="MISMATCH",
                   has_defect=True, defect_fields=["consignee"])
        assert validate(sub, SAMPLE) == []
