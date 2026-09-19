"""Run the clerk's-eye cases as part of the suite.

`eval/desk_cases.py` is the readable report; this keeps it honest on every run
so a normalization tweak cannot quietly reintroduce a false alarm — or worse,
a miss.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from desk_cases import AGREE, CONFLICT, UNDECIDABLE, CASES  # noqa: E402

from sdoc.normalize import values_agree  # noqa: E402

VERDICT = {True: AGREE, False: CONFLICT, None: UNDECIDABLE}


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.field}-{c.why[:38]}")
def test_matches_what_a_clerk_would_say(case):
    got = VERDICT[values_agree(case.field, case.si, case.bl)]
    assert got == case.expect, (
        f"{case.field}: {case.si!r} vs {case.bl!r}\n"
        f"  {case.why}\n  expected {case.expect}, got {got}"
    )


def test_no_case_is_ever_missed():
    """The direction that matters: never call two different things the same."""
    missed = [
        c for c in CASES
        if c.expect == CONFLICT and VERDICT[values_agree(c.field, c.si, c.bl)] != CONFLICT
    ]
    assert not missed, "\n".join(f"{c.field}: {c.why}" for c in missed)


def test_the_suite_still_covers_both_directions():
    """Guard against the file drifting into only-easy cases."""
    assert sum(c.expect == CONFLICT for c in CASES) >= 8
    assert sum(c.expect == AGREE for c in CASES) >= 12
    assert sum(c.severity == "critical" for c in CASES) >= 6
