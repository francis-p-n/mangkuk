"""The seven compared fields, and the many names documents give them.

66 distinct labels appear across the corpus for these seven concepts. This is
the only place that mapping lives.
"""
from __future__ import annotations

import re

FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

# Ordered: first rule that matches wins. Order is load-bearing —
# "Notify Party/Intermediate Consignee" must resolve to notify_party, and
# "Kinds of Packages; Description of Goods" must not resolve to containers.
LABEL_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("notify_party",      ("notify",)),
    ("consignee",         ("consignee", "to the order of")),
    ("shipper",           ("shipper", "exporter", "seller")),
    ("port_of_loading",   ("port of loading", "load port", "pol")),
    ("port_of_discharge", ("port of discharge", "discharge port", "pod")),
    ("container_count",   ("container",)),
    ("gross_weight_kg",   ("gross weight", "gross wt")),
]

_ASCII = re.compile(r"[^\x00-\x7f]")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """'Gross Weight毛重(KGS)' -> 'gross weight kgs'."""
    s = _ASCII.sub(" ", label).lower()
    s = _NONWORD.sub(" ", s)
    return _WS.sub(" ", s).strip()


def label_to_field(label: str) -> str | None:
    norm = normalize_label(label)
    if not norm:
        return None
    for name, markers in LABEL_RULES:
        for m in markers:
            # Short codes (pol/pod) must match the whole label, not a substring,
            # or 'Port of Loading' would hit 'pol' inside another word.
            if len(m) <= 3:
                if norm == m:
                    return name
            elif m in norm:
                return name
    return None
