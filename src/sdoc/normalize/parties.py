"""Shipper, consignee and notify party."""
from __future__ import annotations

import re

from .text import clean

COMPANY_SUFFIXES = (
    "sdn bhd", "pte ltd", "pty ltd", "co ltd", "gmbh", "fz llc", "fzco", "fze",
    "llc", "ltd", "limited", "inc", "bv", "nv", "ag", "sa", "spa", "srl",
    "as", "aps", "ab", "oy", "kft", "doo", "jsc", "plc", "corp", "corporation",
    "company", "joint stock", "pt", "tbk", "sarl", "eood", "uab",
)

_INNER_DOT = re.compile(r"\.(?=\s*[A-Za-z])|(?<=[A-Za-z])\.")


def norm_party(value: str) -> str:
    """Company names, minus legal-form noise and punctuation.

    'Roxcel Trading G.m.b.H.' and 'ROXCEL TRADING GMBH' are the same company;
    so are 'BALL & DOGGETT' and 'BALL AND DOGGETT'.
    """
    s = value.replace("&", " and ")
    s = _INNER_DOT.sub("", s)          # G.m.b.H. -> GmbH, L.L.C. -> LLC
    s = clean(s)
    changed = True
    while changed:
        changed = False
        for suf in COMPANY_SUFFIXES:
            if s.endswith(" " + suf):
                s = s[: -len(suf) - 1].strip()
                changed = True
    return s


def agree(a: str, b: str) -> bool | None:
    na, nb = norm_party(a), norm_party(b)
    if not na or not nb:
        return None
    return na == nb
