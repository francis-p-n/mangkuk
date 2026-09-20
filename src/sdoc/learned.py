"""What the desk has taught the comparator.

The rules in `normalize/` were written by reading documents. A clerk reading
the same documents for a living knows things those rules do not - that two
spellings of a company are the same company, or that two that look alike are
two different legal entities. Today that knowledge is spent on one email and
then lost.

An override records it instead. A clerk disagrees with a verdict, the pair of
values is captured, and from then on the comparator knows it.

Three restrictions, because "the user can teach it" is also how a checker
gets quietly switched off:

1. An override matches one exact pair of values, never a pattern. Teaching it
   about `ROXCEL TRADING GMBH` and `Roxcel Handelsges.m.b.H.` says nothing
   about any other pair, so it cannot silently widen.
2. Overrides are off unless a file is passed. The scored run never sees them,
   and stays reproducible by anyone with the repo.
3. Every override carries who recorded it and when, and applying a set of
   them reports exactly which shipments change verdict before anything is
   written. Nothing about a suppressed defect is quiet.

`tools/apply_overrides.py` then turns each one into a case in the evaluation
suite, so a clerk's judgement outlives the shipment it came from: it becomes
an assertion that has to keep passing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from .normalize import clean

SCHEMA = 1


@dataclass(frozen=True)
class Override:
    """One thing a person said the comparator had wrong."""

    field: str
    si_value: str
    bl_value: str
    agree: bool                  # what the person says is true
    was: bool | None = None      # what the comparator had said
    who: str = ""
    when: str = ""
    note: str = ""

    @property
    def pair(self) -> frozenset[str]:
        """Equivalence has no direction: which document held which value is
        an accident of who typed what."""
        return frozenset({clean(self.si_value), clean(self.bl_value)})

    @property
    def key(self) -> tuple[str, frozenset[str]]:
        return (self.field, self.pair)

    @property
    def suppresses_a_defect(self) -> bool:
        """The dangerous direction: a flag the desk asked us to stop raising."""
        return self.agree is True and self.was is False

    def describe(self) -> str:
        verb = "are the same" if self.agree else "are not the same"
        return f"{self.field}: {self.si_value!r} and {self.bl_value!r} {verb}"

    def to_dict(self) -> dict:
        return {
            "field": self.field, "si_value": self.si_value, "bl_value": self.bl_value,
            "agree": self.agree, "was": self.was, "who": self.who,
            "when": self.when, "note": self.note,
        }


@dataclass
class Overrides:
    """A set of them, indexed for lookup during comparison."""

    entries: list[Override] = dc_field(default_factory=list)

    def __post_init__(self) -> None:
        # Later entries win, so re-teaching a pair corrects it rather than
        # colliding with the earlier answer.
        self._index: dict[tuple[str, frozenset[str]], Override] = {}
        for entry in self.entries:
            self._index[entry.key] = entry

    def __len__(self) -> int:
        return len(self._index)

    def __bool__(self) -> bool:
        return bool(self._index)

    def verdict(self, field_name: str, a: str, b: str) -> bool | None:
        """What the desk says about this exact pair, or None for no opinion."""
        found = self._index.get((field_name, frozenset({clean(a), clean(b)})))
        return None if found is None else found.agree

    @property
    def suppressions(self) -> list[Override]:
        return [e for e in self._index.values() if e.suppresses_a_defect]

    @classmethod
    def from_payload(cls, payload: dict) -> "Overrides":
        if payload.get("schema") != SCHEMA:
            raise ValueError(
                f"overrides file is schema {payload.get('schema')!r}, expected {SCHEMA}")
        seen: list[Override] = []
        for raw in payload.get("overrides", []):
            missing = {"field", "si_value", "bl_value", "agree"} - set(raw)
            if missing:
                raise ValueError(f"override is missing {sorted(missing)}: {raw}")
            if not isinstance(raw["agree"], bool):
                raise ValueError(f"'agree' must be true or false: {raw}")
            # An override is a rule about a pair of values. When both sides
            # normalize to one string there is no pair, and "these are not the
            # same" would apply to every field that reads that value.
            if clean(raw["si_value"]) == clean(raw["bl_value"]):
                raise ValueError(
                    "an override needs two different values; "
                    f"both sides read {raw['si_value']!r}")
            seen.append(Override(
                field=raw["field"], si_value=raw["si_value"], bl_value=raw["bl_value"],
                agree=raw["agree"], was=raw.get("was"), who=raw.get("who", ""),
                when=raw.get("when", ""), note=raw.get("note", ""),
            ))
        return cls(seen)

    @classmethod
    def load(cls, path: str | Path | None) -> "Overrides":
        """Load a file, or an empty set when none is given."""
        if not path:
            return cls([])
        return cls.from_payload(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_payload(self) -> dict:
        return {"schema": SCHEMA,
                "overrides": [e.to_dict() for e in self._index.values()]}
