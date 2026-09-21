"""Thread emails onto shipments.

The OC number is the join key an ops person already thinks in. Booking and BL
references are fallbacks. Nothing is guessed: if no reference is found the
email stays unassigned rather than being attached to the wrong shipment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Every OC in the supplied bundle begins with a 5, and this used to require
# one. That is a fact about this corpus, not about the reference: another
# exporter's series would not match and the email would file itself under
# nothing. Any leading character is accepted now, which finds exactly the same
# 381 references here and does not fall over on the next bundle.
OC_RE = re.compile(r"\b([0-9A-Z][A-Z]{3}-\d{5})\b")

# Booking references are carrier-prefixed, so this is a list of carriers. It is
# a coverage limit rather than a wrong answer: an unknown carrier's booking is
# missed, and a missed reference leaves an email filed on its own instead of
# filed wrongly.
#
# Deliberately not a generic "letters then digits" pattern. A container number
# is four letters, a U and seven digits - indistinguishable by shape from a
# booking - and filing a shipment under a container number would merge
# unrelated mail. This corpus happens to contain none, which is luck rather
# than a reason.
#
# EGLV is Evergreen, written EVER(EGLV...) here. It was absent from the list,
# so 25 emails carrying a perfectly good booking reference filed under nothing.
BOOKING_RE = re.compile(
    r"\b((?:MSDU|MEDU|EGLV|SIN|SIJ|PSGSE|OOLU|YMJAI|MCLSIN|SINF)[A-Z]*\d{6,})\b"
)
INVOICE_RE = re.compile(r"\b(52\d{8})\b")


@dataclass
class Refs:
    oc: str | None = None
    booking: str | None = None
    invoice: str | None = None

    @property
    def key(self) -> str | None:
        return self.oc or self.booking


def find_refs(*texts: str) -> Refs:
    blob = "\n".join(t for t in texts if t)
    oc = OC_RE.search(blob)
    booking = BOOKING_RE.search(blob)
    invoice = INVOICE_RE.search(blob)
    return Refs(
        oc=oc.group(1) if oc else None,
        booking=booking.group(1) if booking else None,
        invoice=invoice.group(1) if invoice else None,
    )
