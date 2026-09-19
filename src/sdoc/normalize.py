"""Per-field normalization and equality. No model involved.

Comparison is the part that must be reproducible, testable and explainable,
so it is ordinary code. The model's job upstream is to *locate* values; this
module decides whether two located values mean the same thing.

The rules here are tuned against `eval/desk_cases.py`, which encodes what an
experienced documentation clerk would call a match. Two directions of error,
weighted very differently:

  a MISS (two different things called the same) puts a wrong value on a bill
  of lading, and is the worst thing this system can do;
  a FALSE ALARM (a difference reported that is not one) costs a clerk a few
  minutes and, repeated often enough, costs their trust in the tool.

Where a rule cannot be made safe in both directions it errs toward flagging.
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

# Box types that mean the same thing on a container. A standard dry box is
# written GP, DV, DC or SD depending on the carrier; a high cube is HC, HQ or
# spelled out. FCL is deliberately kept distinct - it describes the load, not
# the box, and treating it as an alias would hide a real change.
CONTAINER_KINDS = {
    "gp": "DRY", "dv": "DRY", "dc": "DRY", "sd": "DRY", "std": "DRY",
    "hc": "HC", "hq": "HC", "high": "HC", "hicube": "HC",
    "rf": "REEF", "re": "REEF", "reef": "REEF", "rh": "REEF",
    "ot": "OT", "fr": "FR", "tk": "TANK", "fcl": "FCL",
}

# Multipliers to kilograms. A metric tonne is unambiguous; "ton" is not
# (short/long/metric differ by up to 12%), so it is treated as undecidable.
WEIGHT_UNITS = {
    "kg": 1.0, "kgs": 1.0, "kilo": 1.0, "kilos": 1.0, "kilogram": 1.0,
    "kilograms": 1.0, "mt": 1000.0, "mts": 1000.0, "tonne": 1000.0,
    "tonnes": 1000.0, "metrictonne": 1000.0, "metrictonnes": 1000.0,
}
AMBIGUOUS_UNITS = {"ton", "tons", "t", "lb", "lbs"}

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")
_LOCODE = re.compile(r"\(([A-Z]{5})\)")
_CONTAINERS = re.compile(r"(\d+)\s*[xX]\s*(\d+)\s*'?\s*([A-Za-z]+)?")
_INNER_DOT = re.compile(r"\.(?=\s*[A-Za-z])|(?<=[A-Za-z])\.")
_NUMBER = re.compile(r"\d[\d,.\s]*")
_UNIT = re.compile(r"[A-Za-z]+")


def _clean(s: str) -> str:
    return _WS.sub(" ", _PUNCT.sub(" ", s.lower())).strip()


def _edit_distance(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein, short-circuited - only small distances matter here."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def norm_party(value: str) -> str:
    """Company names, minus legal-form noise and punctuation.

    'Roxcel Trading G.m.b.H.' and 'ROXCEL TRADING GMBH' are the same company;
    so are 'BALL & DOGGETT' and 'BALL AND DOGGETT'.
    """
    s = value.replace("&", " and ")
    s = _INNER_DOT.sub("", s)          # G.m.b.H. -> GmbH, L.L.C. -> LLC
    s = _clean(s)
    changed = True
    while changed:
        changed = False
        for suf in COMPANY_SUFFIXES:
            if s.endswith(" " + suf):
                s = s[: -len(suf) - 1].strip()
                changed = True
    return s


def _names_compatible(a: str, b: str) -> bool:
    """Is one port name a reasonable rendering of the other?

    Covers three things a clerk reads straight through: a terminal named on
    one document only ('PORT KLANG (WESTPORT)'), an official name beside a
    common one ('JAWAHARLAL NEHRU (NHAVA SHEVA)'), and spelling drift
    ('KLANG' / 'KELANG').
    """
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    if _edit_distance(a, b, cap=2) <= 2:
        return True
    # A shared distinctive token, e.g. 'nhava sheva' inside a longer name.
    shared = ta & tb
    return bool(shared) and max(len(t) for t in shared) >= 5


@dataclass(frozen=True)
class Port:
    city: str
    country: str
    locode: str

    def conflicts_with(self, other: "Port") -> bool:
        """A missing part is not a conflict; two present-but-different are.

        Country and UN/LOCODE are exact - they are codes, not prose. The city
        name is matched tolerantly, because the same port is written several
        ways. 'MOMBASA, KENYA (KEMBA)' against 'TUTICORIN, INDIA (KEMBA)'
        still conflicts: the countries disagree.
        """
        if self.locode and other.locode and self.locode != other.locode:
            return True
        if self.country and other.country and self.country != other.country:
            return True
        if self.city and other.city and not _names_compatible(self.city, other.city):
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
    raw_kind = (m.group(3) or "").lower()
    kind = CONTAINER_KINDS.get(raw_kind, raw_kind.upper())
    return Containers(int(m.group(1)), m.group(2), kind)


def _number_candidates(text: str) -> list[float]:
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


def _parse_number(text: str) -> float | None:
    candidates = _number_candidates(text)
    return candidates[0] if candidates else None


def weight_candidates(value: str) -> list[float]:
    """Every defensible reading of a weight, in kilograms."""
    number_match = _NUMBER.search(value)
    if not number_match:
        return []
    quantities = _number_candidates(number_match.group())
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
    candidates = weight_candidates(value)
    return candidates[0] if candidates else None


def values_agree(field_name: str, a: str, b: str) -> bool | None:
    """True = same, False = genuine conflict, None = cannot tell from these."""
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
        ca, cb = weight_candidates(a), weight_candidates(b)
        if not ca or not cb:
            return None
        # Where a number can be read two ways, answer only if every reading
        # gives the same verdict. If they disagree, a person decides.
        verdicts = {abs(x - y) < 0.5 for x in ca for y in cb}
        return verdicts.pop() if len(verdicts) == 1 else None

    return _clean(a) == _clean(b)
