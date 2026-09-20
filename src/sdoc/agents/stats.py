"""What the agent stage did, counted.

One number here matters more than the rest. `rate_limited` counts calls that
never got an answer, and it is kept apart from every count of what the model
said, because a throttled run and a model that found nothing look identical
in the output and need completely different fixes. Without it, the first live
run of a well-behaved prompt against a free tier reads as a failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Callable


@dataclass
class AgentStats:
    resolver_calls: int = 0
    fields_requested: int = 0
    fields_returned: int = 0
    fields_accepted: int = 0
    rejected_ungrounded: int = 0
    rejected_implausible: int = 0
    triage_calls: int = 0
    triage_accepted: int = 0
    # Asked, never answered. Not an abstention.
    rate_limited: int = 0
    failed: int = 0
    notes: list[str] = dc_field(default_factory=list)

    # Set by the CLI so a long run says something while it works. Left unset
    # everywhere else, so nothing prints during tests or library use.
    progress: Callable[[str], None] | None = None

    @property
    def calls(self) -> int:
        return self.resolver_calls + self.triage_calls

    @property
    def answered(self) -> int:
        return self.calls - self.rate_limited - self.failed

    @property
    def incomplete(self) -> bool:
        """True when some of what the agent was asked was never answered."""
        return bool(self.rate_limited or self.failed)

    def say(self, message: str) -> None:
        if self.progress:
            self.progress(f"[{self.answered}/{self.calls}] {message}")

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()
                if k not in ("notes", "progress")}
