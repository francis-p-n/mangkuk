"""Severity is a judgement about consequence, so the judgement is pinned here.

These tests are not checking arithmetic. They are checking that the ordering
still says what an operations person was told it says - that a wrong consignee
outranks a wrong container count, and that three cheap errors never add up to
an expensive one. If someone reorders the table, this is where they find out
what they changed.
"""
from __future__ import annotations

import pytest

from conftest import DATA_DIR

from sdoc.fields import FIELDS
from sdoc.mailsource import BundleMailSource
from sdoc.pipeline import run
from sdoc.severity import BANDS, FIELD_RANK, assess, band_for, order, rank_of


class TestTheTableItself:
    def test_every_compared_field_has_a_consequence(self):
        assert set(FIELD_RANK) == set(FIELDS)

    def test_no_two_fields_share_a_rank(self):
        ranks = [r for r, _ in FIELD_RANK.values()]
        assert sorted(ranks) == list(range(1, len(FIELDS) + 1))

    def test_every_field_states_why(self):
        for name, (_, reason) in FIELD_RANK.items():
            assert len(reason) > 20, f"{name} has no real reason recorded"

    def test_bands_cover_every_rank_in_ascending_order(self):
        cutoffs = [c for _, c, _ in BANDS]
        assert cutoffs == sorted(cutoffs)
        assert cutoffs[-1] >= len(FIELD_RANK)


class TestTheOrderingSaysWhatWeClaim:
    @pytest.mark.parametrize("worse,better", [
        ("consignee", "container_count"),
        ("consignee", "notify_party"),
        ("shipper", "port_of_loading"),
        ("port_of_discharge", "port_of_loading"),
        ("gross_weight_kg", "container_count"),
    ])
    def test_relative_order(self, worse, better):
        assert rank_of(worse) < rank_of(better)

    def test_the_two_title_fields_are_critical(self):
        for name in ("consignee", "shipper"):
            assert assess([name]).band == "critical"

    def test_container_count_alone_is_routine(self):
        assert assess(["container_count"]).band == "routine"

    def test_an_unknown_field_sorts_last_rather_than_crashing(self):
        found = assess(["something_new"])
        assert found.rank > len(FIELD_RANK)
        assert found.band == BANDS[-1][0]


class TestADraftIsAsBadAsItsWorstField:
    def test_the_worst_field_decides_the_band(self):
        found = assess(["container_count", "consignee", "port_of_loading"])
        assert found.field == "consignee" and found.band == "critical"

    def test_cheap_errors_do_not_accumulate_into_an_expensive_one(self):
        many_cheap = assess(["container_count", "notify_party", "port_of_loading"])
        one_bad = assess(["consignee"])
        assert many_cheap.sort_key > one_bad.sort_key

    def test_count_only_breaks_ties_within_a_rank(self):
        one = assess(["consignee"])
        two = assess(["consignee", "container_count"])
        assert one.rank == two.rank
        assert two.sort_key < one.sort_key

    def test_a_clean_draft_has_no_severity(self):
        assert assess([]) is None


class TestOrdering:
    def test_worst_first(self):
        rows = [{"defect_fields": ["container_count"]},
                {"defect_fields": ["consignee"]},
                {"defect_fields": ["port_of_discharge"]}]
        assert [r["defect_fields"][0] for r in order(rows)] == [
            "consignee", "port_of_discharge", "container_count"]

    def test_records_without_defects_are_tolerated(self):
        assert len(order([{"defect_fields": []}, {"defect_fields": ["consignee"]}])) == 2


class TestAgainstTheRealRun:
    """The bundle has to produce a queue worth working, not one flat band."""

    def test_every_mismatch_is_banded(self, mismatches):
        assert mismatches
        assert all(r.severity in {n for n, _, _ in BANDS} for r in mismatches)

    def test_clean_and_escalated_drafts_carry_no_band(self, bundle):
        for r in bundle:
            if r.status != "MISMATCH":
                assert r.severity is None, r.email_id

    def test_the_bands_actually_separate_the_queue(self, mismatches):
        seen = {r.severity for r in mismatches}
        assert len(seen) == 3, f"severity is not discriminating: {seen}"

    def test_every_banded_draft_can_say_why(self, mismatches):
        for r in mismatches:
            assert r.severity_field in r.defect_fields, r.email_id
            assert r.severity_reason, r.email_id


@pytest.fixture(scope="module")
def bundle():
    return run(BundleMailSource(DATA_DIR))


@pytest.fixture(scope="module")
def mismatches(bundle):
    return [r for r in bundle if r.status == "MISMATCH"]
