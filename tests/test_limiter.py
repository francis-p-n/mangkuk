"""The limiter paces calls and stops at a budget.

Driven by a fake clock throughout: a test that proves a nine-per-minute pace
by living through it takes seven minutes, and a test nobody waits for is a
test nobody runs.
"""
from __future__ import annotations

import pytest

from sdoc.agents.limiter import BudgetExhausted, Limiter


class Clock:
    """A clock that only moves when something sleeps on it."""

    def __init__(self):
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds

    def tick(self, seconds: float) -> None:
        """Time passing for a reason other than waiting - the work itself."""
        self.t += seconds


def limiter(rpm=60, budget=100, clock=None):
    c = clock or Clock()
    return Limiter(rpm=rpm, budget=budget, sleep=c.sleep, now=c.now), c


class TestPacing:
    def test_the_first_call_does_not_wait(self):
        lim, c = limiter(rpm=6)
        lim.acquire()
        assert c.slept == []

    def test_a_burst_is_spaced_to_the_allowance(self):
        lim, c = limiter(rpm=6)          # one call every ten seconds
        for _ in range(4):
            lim.acquire()
        assert c.slept == [10.0, 10.0, 10.0]
        assert c.now() == pytest.approx(30.0)

    def test_work_already_done_counts_towards_the_gap(self):
        """A call that took eight seconds has already waited eight seconds."""
        lim, c = limiter(rpm=6)
        lim.acquire()
        c.tick(8.0)
        lim.acquire()
        assert c.slept == [pytest.approx(2.0)]

    def test_a_slow_call_means_no_wait_at_all(self):
        lim, c = limiter(rpm=6)
        lim.acquire()
        c.tick(30.0)
        lim.acquire()
        assert c.slept == []

    def test_rpm_of_zero_does_not_pace(self):
        """An escape hatch for a paid tier, and it must not divide by zero."""
        lim, c = limiter(rpm=0)
        for _ in range(5):
            lim.acquire()
        assert c.slept == []


class TestBudget:
    def test_it_stops_when_the_budget_is_spent(self):
        lim, _ = limiter(rpm=0, budget=3)
        for _ in range(3):
            lim.acquire()
        with pytest.raises(BudgetExhausted):
            lim.acquire()

    def test_the_refusal_names_the_setting_that_changes_it(self):
        lim, _ = limiter(rpm=0, budget=1)
        lim.acquire()
        with pytest.raises(BudgetExhausted, match="SDOC_AGENT_BUDGET"):
            lim.acquire()

    def test_a_refused_call_is_not_counted_or_slept_on(self):
        """Being refused must not cost a slot, or the budget shrinks itself."""
        lim, c = limiter(rpm=6, budget=2)
        lim.acquire()
        lim.acquire()
        before = (lim.spent, len(c.slept))
        for _ in range(3):
            with pytest.raises(BudgetExhausted):
                lim.acquire()
        assert (lim.spent, len(c.slept)) == before

    def test_left_reports_what_remains(self):
        lim, _ = limiter(rpm=0, budget=3)
        assert lim.left == 3
        lim.acquire()
        assert lim.left == 2

    def test_budget_is_checked_before_waiting(self):
        """Sleeping ten seconds to then be refused helps nobody."""
        lim, c = limiter(rpm=6, budget=1)
        lim.acquire()
        with pytest.raises(BudgetExhausted):
            lim.acquire()
        assert c.slept == []


class TestReporting:
    def test_it_says_what_it_did(self):
        lim, _ = limiter(rpm=6, budget=10)
        for _ in range(3):
            lim.acquire()
        s = lim.summary()
        assert "3 call(s) of 10" in s and "6/min" in s and "20s" in s

    def test_a_run_that_made_no_calls_says_so(self):
        lim, _ = limiter()
        assert lim.summary() == "no calls made"
