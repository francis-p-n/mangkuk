"""Asking slowly enough to be answered, and stopping before the day is spent.

Two different limits, and confusing them wastes a quota.

*Per minute* is a pace. Exceeding it is temporary: wait a moment and the same
request succeeds. The fix is to not ask that fast, which is what a spacer
does - it holds each call back until enough time has passed since the last.

*Per day* is a budget. Exceeding it is not temporary and no amount of waiting
inside one run will clear it. The fix is to stop asking, and to stop while
there is still something left for the next run rather than discovering the
wall at email four hundred.

Before this, a run fired as fast as the loop could go, took the 429s, and
slept through the backoff on every one of them. That is the same number of
requests arriving in the same minute - the retry loop made the burst longer,
not smaller.
"""
from __future__ import annotations

import os
import threading
import time

# Google's free tier allows ten generateContent calls a minute on the flash
# models. Nine leaves room for the clock disagreeing slightly about when a
# minute began, which is cheaper than finding out by being refused.
DEFAULT_RPM = int(os.environ.get("SDOC_AGENT_RPM", "9"))

# A full run against the supplied bundle asks for about 72 calls. The default
# budget is above that so a normal run is never truncated, and finite so a
# corpus ten times the size cannot silently spend a day's quota discovering
# that it is ten times the size.
DEFAULT_BUDGET = int(os.environ.get("SDOC_AGENT_BUDGET", "200"))


class BudgetExhausted(RuntimeError):
    """The run has asked as many times as it is allowed to.

    Kept apart from being throttled: throttling is the provider saying "not
    yet", and this is us saying "not at all". Only one of them is worth
    retrying, and a run that cannot tell them apart will retry the wrong one.
    """


class Limiter:
    """Spaces calls out, and counts them against a budget.

    One instance per run, shared by every agent, because the quota is shared
    by every agent: a triage call and a resolver call are the same request as
    far as the provider is concerned.
    """

    def __init__(self, rpm: int = DEFAULT_RPM, budget: int = DEFAULT_BUDGET,
                 sleep=time.sleep, now=time.monotonic):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self.budget = budget
        self.spent = 0
        self.waited = 0.0
        # Injected so a test can drive the clock rather than live through it.
        self._sleep = sleep
        self._now = now
        # None rather than 0.0: a timestamp of zero is a real instant, and
        # testing it for truth makes the first gap vanish whenever the clock
        # happens to start there.
        self._last: float | None = None
        self._lock = threading.Lock()

    @property
    def left(self) -> int:
        return max(0, self.budget - self.spent)

    def acquire(self) -> None:
        """Block until another call is allowed, or refuse if none are left."""
        with self._lock:
            if self.spent >= self.budget:
                raise BudgetExhausted(
                    f"this run has used its {self.budget} call budget - raise "
                    f"SDOC_AGENT_BUDGET to allow more"
                )
            if self.interval and self._last is not None:
                # monotonic, so the wait is not confused by the system clock
                # being corrected mid-run.
                gap = self._now() - self._last
                if gap < self.interval:
                    wait = self.interval - gap
                    self.waited += wait
                    self._sleep(wait)
            self._last = self._now()
            self.spent += 1

    def summary(self) -> str:
        if not self.spent:
            return "no calls made"
        rate = f"{60 / self.interval:.0f}/min" if self.interval else "unpaced"
        return (f"{self.spent} call(s) of {self.budget}, paced at {rate}"
                + (f", {self.waited:.0f}s spent waiting" if self.waited else ""))
