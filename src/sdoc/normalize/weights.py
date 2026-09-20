"""Gross weight, in whatever unit the document used."""
from __future__ import annotations

import re

from . import numbers

# Multipliers to kilograms. A metric tonne is unambiguous; "ton" is not
# (short/long/metric differ by up to 12%), so it is treated as undecidable.
WEIGHT_UNITS = {
    "kg": 1.0, "kgs": 1.0, "kilo": 1.0, "kilos": 1.0, "kilogram": 1.0,
    "kilograms": 1.0, "mt": 1000.0, "mts": 1000.0, "tonne": 1000.0,
    "tonnes": 1000.0, "metrictonne": 1000.0, "metrictonnes": 1000.0,
}
AMBIGUOUS_UNITS = {"ton", "tons", "t", "lb", "lbs"}

_NUMBER = re.compile(r"\d[\d,.\s]*")
_UNIT = re.compile(r"[A-Za-z]+")


def weight_candidates(value: str) -> list[float]:
    """Every defensible reading of a weight, in kilograms."""
    number_match = _NUMBER.search(value)
    if not number_match:
        return []
    quantities = numbers.candidates(number_match.group())
    if not quantities:
        return []

    tail = value[number_match.end():]
    unit_token = "".join(_UNIT.findall(tail)).lower() or \
                 "".join(_UNIT.findall(value[: number_match.start()])).lower()
    if unit_token in AMBIGUOUS_UNITS:
        return []                        # 'ton' is not one thing - escalate
    multiplier = WEIGHT_UNITS.get(unit_token, 1.0)
    return [q * multiplier for q in quantities]


def parse_weight(value: str) -> float | None:
    """Weight in kilograms under the most likely reading, or None."""
    found = weight_candidates(value)
    return found[0] if found else None


def agree(a: str, b: str) -> bool | None:
    ca, cb = weight_candidates(a), weight_candidates(b)
    if not ca or not cb:
        return None
    # Where a number can be read two ways, answer only if every reading gives
    # the same verdict. If they disagree, a person decides.
    verdicts = {abs(x - y) < 0.5 for x in ca for y in cb}
    return verdicts.pop() if len(verdicts) == 1 else None
