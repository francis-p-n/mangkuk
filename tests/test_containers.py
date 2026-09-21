"""Box types, against the codes carriers actually write.

The bundle only ever uses GP, DV, HC, RF and FCL, so the corpus cannot tell a
table that knows shipping from one that knows this corpus. These are the rest
of ISO 6346, and the two failure directions are not equally bad: waving a real
difference through puts the wrong equipment under the cargo, and inventing one
sends a clerk to argue with a carrier about spelling.
"""
from __future__ import annotations

import pytest

from sdoc.normalize.containers import agree, parse_containers


class TestSameBoxWrittenDifferently:
    """Must not be reported as a difference."""

    @pytest.mark.parametrize("a,b", [
        ("10 x 20'GP", "10 x 20'DV"),
        ("10 x 20'GP", "10 x 20'DC"),
        ("10 x 20'GP", "10 x 20'SD"),
        ("6 x 40'HC", "6 x 40'HQ"),
        ("6 x 40'HC", "6 x 40'HIGH CUBE"),
        ("2 x 20'RF", "2 x 20'REEFER"),
        ("4 x 40'PL", "4 x 40'PLATFORM"),
        ("4 x 40'VH", "4 x 40'VENTILATED"),
        ("4 x 40'BU", "4 x 40'BULK"),
        ("4 x 40'OT", "4 x 40'OPEN TOP"),
        ("4 x 40'TK", "4 x 40'TANK"),
    ])
    def test_spellings_of_one_box_agree(self, a, b):
        assert agree(a, b) is True


class TestDifferentBoxes:
    """Must be reported. These change what the cargo travels in."""

    @pytest.mark.parametrize("a,b,why", [
        ("6 x 40'GP", "6 x 40'HC", "a high cube is a foot taller"),
        ("2 x 20'RF", "2 x 20'RH", "a reefer high cube is not a reefer"),
        ("2 x 20'GP", "2 x 20'RF", "dry is not refrigerated"),
        ("2 x 20'OT", "2 x 20'FR", "open top is not a flat rack"),
        ("2 x 20'GP", "2 x 20'TK", "a tank is not a box"),
    ])
    def test_real_differences_are_reported(self, a, b, why):
        assert agree(a, b) is False, why

    def test_a_reefer_high_cube_is_not_folded_in_with_reefers(self):
        """Regression: RH was aliased to REEF, so this passed silently."""
        assert parse_containers("2 x 40'RH").kind != parse_containers("2 x 40'RF").kind

    @pytest.mark.parametrize("a,b", [
        ("9 x 20'GP", "10 x 20'GP"),
        ("10 x 20'GP", "10 x 40'GP"),
    ])
    def test_count_and_size_still_decide(self, a, b):
        assert agree(a, b) is False


class TestAirFreight:
    """Unit load devices are refused, not guessed at.

    An AKE is a contoured LD3 and a PMC is a pallet. Nothing here models the
    difference, and the parser used to read "3 x AKE" as a bare count of
    three - so two different ULDs agreed on the count and had nothing left to
    disagree about. A silent wrong answer on a document this tool has no
    business judging.
    """

    @pytest.mark.parametrize("uld", ["AKE", "AMA", "PMC", "PAG", "LD3", "LD7"])
    def test_a_uld_is_not_read_as_a_container(self, uld):
        assert parse_containers(f"3 x {uld}") is None

    def test_two_different_ulds_do_not_agree(self):
        assert agree("3 x AKE", "3 x PMC") is None

    def test_even_identical_ulds_are_refused(self):
        """Agreeing for the right reason by accident is still not knowing."""
        assert agree("3 x AKE", "3 x AKE") is None


class TestFCL:
    def test_fcl_is_not_a_box_type(self):
        """It describes the load, not the equipment, so it is kept distinct."""
        assert agree("10 x 20'FCL", "10 x 20'GP") is False


class TestSizes:
    @pytest.mark.parametrize("size", ["10", "20", "30", "40", "45", "48", "53"])
    def test_every_size_in_use_parses(self, size):
        c = parse_containers(f"2 x {size}'HC")
        assert c is not None and c.size == size and c.count == 2
