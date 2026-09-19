"""Thread emails onto shipments.

The OC number is the join key an ops person already thinks in. Booking and BL
references are fallbacks. Nothing is guessed: if no reference is found the
email stays unassigned rather than being attached to the wrong shipment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

OC_RE = re.compile(r"\b(5[A-Z]{3}-\d{5})\b")
BOOKING_RE = re.compile(r"\b((?:MSDU|MEDU|SIN|SIJ|PSGSE|OOLU|YMJAI|MCLSIN|SINF)[A-Z]*\d{6,})\b")
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
