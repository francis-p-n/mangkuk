"""Descriptive fields for the shipment card. Never compared."""
from __future__ import annotations

from .aliases import label_to_field, normalize_label

# Context shown on the shipment card. Never compared — these exist so a person
# can recognise the shipment, not so the machine can judge it.
CONTEXT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("vessel",     ("vessel", "export carrier", "ocean vessel")),
    ("voyage",     ("voyage", "voy no", "voy")),
    ("commodity",  ("commodity", "description of goods", "description")),
    ("bl_number",  ("bill of lading no", "b l no", "b l number", "bl no")),
    ("booking",    ("booking",)),
    ("oc_number",  ("oc no",)),
]


def extract_context(text: str) -> dict[str, str]:
    """Descriptive fields for the shipment card, first occurrence wins."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        label, _, value = raw.partition(":")
        norm, value = normalize_label(label), value.strip()
        if not norm or not value or label_to_field(label):
            continue
        for name, markers in CONTEXT_RULES:
            if name in found:
                continue
            if any(norm == m or norm.startswith(m) or m in norm for m in markers):
                found[name] = value
                break
    return found
