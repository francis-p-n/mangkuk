"""Loading and discharge ports.

A port is three facts that disagree independently: a city name written several
ways, a country, and a UN/LOCODE. Codes are compared exactly; the name is
matched tolerantly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .text import clean, edit_distance

_LOCODE = re.compile(r"\(([A-Z]{5})\)")


def names_compatible(a: str, b: str) -> bool:
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
    if edit_distance(a, b, cap=2) <= 2:
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
        if self.city and other.city and not names_compatible(self.city, other.city):
            return True
        return False


def parse_port(value: str) -> Port:
    locode_match = _LOCODE.search(value)
    locode = locode_match.group(1) if locode_match else ""
    without = _LOCODE.sub("", value)
    parts = [clean(p) for p in without.split(",") if clean(p)]
    city = parts[0] if parts else ""
    country = parts[-1] if len(parts) > 1 else ""
    return Port(city=city, country=country, locode=locode)


def agree(a: str, b: str) -> bool | None:
    pa, pb = parse_port(a), parse_port(b)
    if not (pa.city or pa.locode) or not (pb.city or pb.locode):
        return None
    return not pa.conflicts_with(pb)
