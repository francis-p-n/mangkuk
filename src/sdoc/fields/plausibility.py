"""A sanity check for values found without a label to anchor them."""
from __future__ import annotations

import re

# A quantity looks like a quantity: digits, separators, then at most a unit.
# Shape is checked as well as parseability, because a parser hunting for the
# first number in a sentence will happily find one in "the vessel is SOLID 16".
_WEIGHT_SHAPE = re.compile(r"^\d[\d,.\s]*[A-Za-z]{0,12}\.?$")
_CONTAINER_SHAPE = re.compile(r"^\s*\d+\s*[xX]\s*\d+")


def plausible(name: str, value: str) -> bool:
    """Sanity guard for values found without a colon to anchor them.

    Applies to the block-layout pass and to anything the agent proposes —
    the two places where a value is not pinned to its own label.
    """
    from ..normalize import parse_containers, parse_weight

    value = value.strip()
    if name == "gross_weight_kg":
        return bool(_WEIGHT_SHAPE.match(value)) and parse_weight(value) is not None
    if name == "container_count":
        return bool(_CONTAINER_SHAPE.match(value)) and parse_containers(value) is not None
    return len(value) > 2 and any(ch.isalpha() for ch in value)
