"""What the agent stage did, counted."""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field


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
    notes: list[str] = dc_field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "notes"}
