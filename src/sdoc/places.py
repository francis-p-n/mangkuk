"""Canonical names for the places a shipment touches.

The documents write the same port several ways — `APAPA, NIGERIA` on one and
`APAPA, NIGERIA (NGAPP)` on another — which is harmless for comparison (the
comparator already reads through it) but useless for a filter: the same
destination appears twice in the list and each one hides half the shipments.

So the corpus teaches itself. Every port that appears with a UN/LOCODE
contributes that code to a lookup, and ports written without one borrow it.
Nothing is invented: a city that never appears with a code simply keeps its
name.
"""
from __future__ import annotations

import re

from .normalize import parse_port

# Segments of an address that are not a place.
_PHONE = re.compile(r"^(t|tel|telephone|fax|f|p|phone)\b[\s.:]*|^[\d\s+()\-]+$", re.I)
_POSTCODE_ONLY = re.compile(r"^[\d\s\-]+$")

# Written several ways across the corpus; the desk says the right-hand version.
COUNTRY_ALIASES = {
    "uae": "United Arab Emirates",
    "u a e": "United Arab Emirates",
    "usa": "United States",
    "us": "United States",
    "u s a": "United States",
    "uk": "United Kingdom",
    "korea": "South Korea",
    "republic of korea": "South Korea",
    "prc": "China",
}


def _tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,.;").strip()


def country_from_address(address: str) -> str:
    """The country at the end of a party's address block, if there is one.

    Addresses arrive as semicolon-separated lines with the country last, but a
    phone number is often appended after it, so segments are walked backwards
    until one looks like a place.
    """
    if not address:
        return ""
    chunks: list[str] = []
    for line in address.split(";"):
        chunks.extend(part for part in line.split(",") if part.strip())

    for chunk in reversed(chunks):
        candidate = _tidy(chunk)
        if not candidate or _PHONE.match(candidate) or _POSTCODE_ONLY.match(candidate):
            continue
        # Trailing postcode on the same segment, e.g. "ENFIELD NSW 2136".
        words = [w for w in candidate.split() if not w.isdigit()]
        if not words:
            continue
        name = " ".join(words)
        return COUNTRY_ALIASES.get(name.lower(), name.title())
    return ""


class PlaceBook:
    """Learns each port's UN/LOCODE from the documents that bother to state it."""

    def __init__(self) -> None:
        self._codes: dict[tuple[str, str], str] = {}

    def learn(self, value: str) -> None:
        if not value:
            return
        port = parse_port(value)
        if port.locode and port.city:
            self._codes.setdefault((port.city, port.country), port.locode)

    def canonical(self, value: str) -> dict:
        """A single settled spelling, plus the parts, for one port string."""
        if not value:
            return {"name": "", "city": "", "country": "", "locode": ""}
        port = parse_port(value)
        locode = port.locode or self._codes.get((port.city, port.country), "")
        city = port.city.title()
        country = COUNTRY_ALIASES.get(port.country, port.country.title())
        name = ", ".join(p for p in (city, country) if p)
        return {
            "name": f"{name} ({locode})" if locode and name else name,
            "city": city,
            "country": country,
            "locode": locode,
        }
