"""Per-field normalization and equality. No model involved.

Comparison is the part that must be reproducible, testable and explainable,
so it is ordinary code. The model's job upstream is to *locate* values; this
module decides whether two located values mean the same thing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

COMPANY_SUFFIXES = (
    "sdn bhd", "pte ltd", "pty ltd", "co ltd", "gmbh", "fz llc", "fzco", "fze",
    "llc", "ltd", "limited", "inc", "bv", "nv", "ag", "sa", "spa", "srl",
    "as", "aps", "ab", "oy", "kft", "doo", "jsc", "plc", "corp", "corporation",
    "company", "joint stock", "pt", "tbk", "sarl", "eood", "uab",
)

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")
_LOCODE = re.compile(r"\(([A-Z]{5})\)")
_CONTAINERS = re.compile(r"(\d+)\s*[xX]\s*(\d+)\s*'?\s*([A-Za-z]{2,4})")
_WEIGHT = re.compile(r"([\d,.\s]+)")


def _clean(s: str) -> str:
    return _WS.sub(" ", _PUNCT.sub(" ", s.lower())).strip()


def norm_party(value: str) -> str:
    """Company names, minus legal-form noise and punctuation."""
    s = _clean(value)
    changed = True
    while changed:
        changed = False
        for suf in COMPANY_SUFFIXES:
            if s.endswith(" " + suf):
                s = s[: -len(suf) - 1].strip()
                changed = True
    return s


@dataclass(frozen=True)
class Port:
    city: str
    country: str
    locode: str

    def conflicts_with(self, other: "Port") -> bool:
        """A missing part is not a conflict; two present-but-different parts are.

        This is what catches 'TUTICORIN, INDIA (KEMBA)' — the city agrees while
        the UN/LOCODE points at Mombasa.
        """
        for a, b in ((self.city, other.city), (self.country, other.country), (self.locode, other.locode)):
            if a and b and a != b:
                return True
        return False


def parse_port(value: str) -> Port:
    locode_match = _LOCODE.search(value)
    locode = locode_match.group(1) if locode_match else ""
    without = _LOCODE.sub("", value)
    parts = [_clean(p) for p in without.split(",") if _clean(p)]
    city = parts[0] if parts else ""
    country = parts[-1] if len(parts) > 1 else ""
    return Port(city=city, country=country, locode=locode)


@dataclass(frozen=True)
class Containers:
    count: int
    size: str
    kind: str


def parse_containers(value: str) -> Containers | None:
    m = _CONTAINERS.search(value)
    if not m:
        digits = re.search(r"\d+", value)
        return Containers(int(digits.group()), "", "") if digits else None
    return Containers(int(m.group(1)), m.group(2), m.group(3).upper())


def parse_weight(value: str) -> float | None:
    m = _WEIGHT.search(value.replace("KGS", "").replace("KG", "").replace("kgs", "").replace("kg", ""))
    if not m:
        return None
    cleaned = m.group(1).replace(",", "").replace(" ", "").strip().rstrip(".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def values_agree(field_name: str, a: str, b: str) -> bool | None:
    """True = same, False = genuine conflict, None = cannot tell from these values."""
    if field_name in ("shipper", "consignee", "notify_party"):
        na, nb = norm_party(a), norm_party(b)
        if not na or not nb:
            return None
        return na == nb

    if field_name in ("port_of_loading", "port_of_discharge"):
        pa, pb = parse_port(a), parse_port(b)
        if not (pa.city or pa.locode) or not (pb.city or pb.locode):
            return None
        return not pa.conflicts_with(pb)

    if field_name == "container_count":
        ca, cb = parse_containers(a), parse_containers(b)
        if ca is None or cb is None:
            return None
        if ca.count != cb.count:
            return False
        if ca.size and cb.size and ca.size != cb.size:
            return False
        if ca.kind and cb.kind and ca.kind != cb.kind:
            return False
        return True

    if field_name == "gross_weight_kg":
        wa, wb = parse_weight(a), parse_weight(b)
        if wa is None or wb is None:
            return None
        return abs(wa - wb) < 0.5

    return _clean(a) == _clean(b)
