"""Corrections the desk records, and the limits on what they can do.

"Let the user teach it" is also the shape of a checker being quietly switched
off, so most of what is asserted here is what an override *cannot* do: reach
a pair it was not taught, reach another field, invent a value the parsers
never found, or affect a run that did not ask for it.
"""
from __future__ import annotations

import json

import pytest

from conftest import DATA_DIR

from sdoc.compare import compare_fieldsets
from sdoc.fields import Extracted, FieldSet
from sdoc.learned import Override, Overrides
from sdoc.mailsource import BundleMailSource
from sdoc.pipeline import run

ROXCEL = ("Roxcel Trading G.m.b.H.", "ROXCEL HANDELSGES MBH")


def payload(*entries: dict) -> dict:
    return {"schema": 1, "overrides": list(entries)}


def one(field="consignee", si="ALPHA TRADING", bl="BETA SHIPPING",
        agree=True, was=False, **extra) -> dict:
    return {"field": field, "si_value": si, "bl_value": bl,
            "agree": agree, "was": was, **extra}


def fieldset(**values) -> FieldSet:
    return FieldSet(values={
        k: Extracted(value=v, label=k, line_no=1, raw_line=f"{k}: {v}")
        for k, v in values.items()})


class TestLoading:
    def test_no_file_is_an_empty_set(self):
        assert not Overrides.load(None)
        assert len(Overrides.load("")) == 0

    def test_a_file_round_trips(self, tmp_path):
        path = tmp_path / "overrides.json"
        path.write_text(json.dumps(payload(one())), encoding="utf-8")
        assert len(Overrides.load(path)) == 1

    def test_the_shipped_file_is_valid(self):
        """The example in the repo has to keep loading, or the demo dies."""
        root = DATA_DIR.parent
        loaded = Overrides.load(root / "overrides.json")
        assert len(loaded) >= 1
        assert all(e.who for e in loaded.entries), "every correction names who made it"

    @pytest.mark.parametrize("bad,because", [
        ({"schema": 99, "overrides": []}, "unknown schema"),
        (payload({"field": "consignee", "si_value": "A"}), "missing keys"),
        (payload(one(agree="yes")), "agree is not a boolean"),
        (payload(one(si="SAME CO", bl="SAME CO")), "both sides are one value"),
        (payload(one(si="SAME CO", bl="  same co  ")), "both sides normalize to one value"),
    ])
    def test_a_bad_file_is_refused(self, bad, because):
        with pytest.raises(ValueError):
            Overrides.from_payload(bad)


class TestWhatAnOverrideReaches:
    @pytest.fixture
    def taught(self):
        return Overrides.from_payload(payload(one(si=ROXCEL[0], bl=ROXCEL[1])))

    def test_the_pair_it_was_taught(self, taught):
        assert taught.verdict("consignee", *ROXCEL) is True

    def test_the_same_pair_the_other_way_round(self, taught):
        """Which document held which value is an accident of who typed what."""
        assert taught.verdict("consignee", ROXCEL[1], ROXCEL[0]) is True

    def test_not_a_different_field(self, taught):
        assert taught.verdict("shipper", *ROXCEL) is None

    def test_not_a_different_pair(self, taught):
        assert taught.verdict("consignee", ROXCEL[0], "SOMEBODY ELSE LTD") is None

    def test_it_does_not_generalise_to_similar_names(self, taught):
        """The point of pair-matching: teaching one pair teaches only it."""
        assert taught.verdict("consignee", "ROXCEL TRADING GMBH", "ROXCEL SHIPPING GMBH") is None

    def test_re_teaching_a_pair_replaces_the_answer(self):
        loaded = Overrides.from_payload(payload(
            one(si=ROXCEL[0], bl=ROXCEL[1], agree=True),
            one(si=ROXCEL[0], bl=ROXCEL[1], agree=False),
        ))
        assert len(loaded) == 1
        assert loaded.verdict("consignee", *ROXCEL) is False


class TestSuppressionIsCalledOut:
    def test_silencing_a_flag_is_identified(self):
        loaded = Overrides.from_payload(payload(one(agree=True, was=False)))
        assert len(loaded.suppressions) == 1

    def test_raising_a_new_flag_is_not_a_suppression(self):
        loaded = Overrides.from_payload(payload(one(agree=False, was=True)))
        assert loaded.suppressions == []

    def test_an_override_knows_which_direction_it_is(self):
        entry = Override("consignee", "A CO", "B CO", agree=True, was=False)
        assert entry.suppresses_a_defect
        assert "are the same" in entry.describe()


class TestTheComparatorHonoursThem:
    SI = dict(shipper="ALPHA TRADING", consignee="ALPHA TRADING",
              notify_party="ALPHA TRADING", port_of_loading="SINGAPORE",
              port_of_discharge="KARACHI", container_count="3 x 40'HC",
              gross_weight_kg="21,577 KG")

    def both(self, **si_changes):
        si = fieldset(**{**self.SI, **si_changes})
        bl = fieldset(**self.SI)
        return si, bl

    def test_without_overrides_a_conflict_stands(self):
        si, bl = self.both(consignee="BETA SHIPPING")
        assert compare_fieldsets(si, bl).status == "MISMATCH"

    def test_an_override_can_settle_it(self):
        si, bl = self.both(consignee="BETA SHIPPING")
        taught = Overrides.from_payload(payload(
            one(si="BETA SHIPPING", bl="ALPHA TRADING", agree=True, was=False)))
        assert compare_fieldsets(si, bl, taught).status == "OK"

    def test_an_override_can_raise_a_flag_the_rules_missed(self):
        si, bl = self.both()
        taught = Overrides.from_payload(payload(one(
            field="port_of_loading", si="SINGAPORE", bl="SINGAPORE (SGSIN)",
            agree=False, was=True)))
        si = fieldset(**{**self.SI, "port_of_loading": "SINGAPORE (SGSIN)"})
        got = compare_fieldsets(si, fieldset(**self.SI), taught)
        assert got.status == "MISMATCH" and got.defect_fields == ["port_of_loading"]

    def test_the_overruled_row_says_so(self):
        si, bl = self.both(consignee="BETA SHIPPING")
        taught = Overrides.from_payload(payload(
            one(si="BETA SHIPPING", bl="ALPHA TRADING", agree=True, was=False)))
        rows = {c.field: c for c in compare_fieldsets(si, bl, taught).comparisons}
        assert rows["consignee"].taught is True
        assert rows["shipper"].taught is False, "only the taught pair is marked"

    def test_an_override_cannot_supply_a_field_nobody_found(self):
        """It settles a disagreement. It is not a source of values."""
        si = fieldset(**{k: v for k, v in self.SI.items() if k != "consignee"})
        taught = Overrides.from_payload(payload(
            one(si="ALPHA TRADING", bl="ALPHA TRADING CO", agree=True)))
        got = compare_fieldsets(si, fieldset(**self.SI), taught)
        assert got.status == "NEEDS_REVIEW"
        assert got.review_reason == "missing_value"


class TestTheScoredRunIsUntouched:
    """Whatever the desk records, `python run.py` with no flag must not move."""

    def test_the_whole_inbox_is_identical_without_overrides(self):
        plain = run(BundleMailSource(DATA_DIR))
        empty = run(BundleMailSource(DATA_DIR), learned=Overrides([]))
        assert [r.to_submission() for r in plain] == [r.to_submission() for r in empty]

    def test_nothing_is_marked_taught_by_default(self):
        for r in run(BundleMailSource(DATA_DIR)):
            assert not any(c["taught"] for c in r.comparisons), r.email_id
