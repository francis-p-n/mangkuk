"""Reading a written quantity, in either grouping convention."""
from __future__ import annotations

import re


def candidates(text: str) -> list[float]:
    """Every reading of a written quantity, most likely first.

    '21,577.00' and '21.577,00' are unambiguous - the later separator is the
    decimal point. A lone dot before exactly three digits is not: '21.577' is
    21577 to a German freight forwarder and 21.577 to everyone else. Both
    readings are returned so the caller can refuse to guess.
    """
    s = text.replace(" ", "").strip().rstrip(".,")
    if not s:
        return []

    def _f(v: str) -> float | None:
        try:
            return float(v)
        except ValueError:
            return None

    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot != -1 and last_comma != -1:
        fixed = s.replace(".", "").replace(",", ".") if last_comma > last_dot \
            else s.replace(",", "")
        value = _f(fixed)
        return [value] if value is not None else []

    if last_comma != -1:
        # Comma grouping is the convention across this corpus and in
        # English-language shipping documents; treat it as settled.
        fixed = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) \
            else s.replace(",", ".")
        value = _f(fixed)
        return [value] if value is not None else []

    if last_dot != -1 and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        both = [_f(s.replace(".", "")), _f(s)]
        return [v for v in both if v is not None]

    value = _f(s)
    return [value] if value is not None else []


def parse(text: str) -> float | None:
    """The most likely reading, or None."""
    found = candidates(text)
    return found[0] if found else None
