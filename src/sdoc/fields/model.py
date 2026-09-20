"""What an extracted value carries with it."""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from .aliases import FIELDS

@dataclass
class Extracted:
    """One field value plus where it came from."""

    value: str
    label: str
    line_no: int
    raw_line: str
    detail: str = ""     # continuation line, e.g. a party's address


@dataclass
class FieldSet:
    values: dict[str, Extracted] = dc_field(default_factory=dict)

    def get(self, name: str) -> Extracted | None:
        return self.values.get(name)

    @property
    def missing(self) -> list[str]:
        return [f for f in FIELDS if f not in self.values]
