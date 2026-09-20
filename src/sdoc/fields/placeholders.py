"""Telling an unfilled form field from a stated value."""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")

# An unfilled form field is not a value. Templates arrive with the blanks still
# in them - "Port of Loading (POL): ____MT" alongside "NET WEIGHT: _______ MTS" -
# and "TBA" means the desk has not decided yet. Treating either as a stated
# value turns an unfinished instruction into a false discrepancy report.
_BLANK_RUN = re.compile(r"^[_\-.?*x\s]*[_\-?*]{2,}[_\-.?*\s]*[A-Za-z]{0,4}\.?$", re.I)
_PLACEHOLDER_WORDS = {
    "tba", "tbc", "tbd", "t b a", "to be advised", "to be confirmed",
    "to be nominated", "n/a", "na", "n a", "nil", "none", "null", "pending",
    "unknown", "xxx", "xx", "same as above", "as above",
}


def is_placeholder(value: str) -> bool:
    """True when a field is present on the form but has not been filled in."""
    text = value.strip()
    if not text:
        return True
    if _BLANK_RUN.match(text):
        return True
    squashed = _WS.sub(" ", text.lower().strip(" .:-")).strip()
    if squashed in _PLACEHOLDER_WORDS:
        return True
    # "T.B.A." and "N/A" are the same tokens with punctuation sprinkled in.
    compact = re.sub(r"[^a-z]", "", squashed)
    return compact in {"tba", "tbc", "tbd", "na", "nil", "none", "null",
                       "pending", "unknown", "xxx", "xx", "tobeadvised",
                       "tobeconfirmed", "tobenominated"}
