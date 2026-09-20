"""Pull the seven compared fields out of a document, with evidence.

The SI and the BL label the same thing differently, so alignment is by
meaning, never by header text. Every extracted value carries the exact source
line that produced it, so a human can check the machine instead of trusting it.

    aliases.py       the seven fields and the labels that mean them
    model.py         Extracted and FieldSet
    placeholders.py  an unfilled form field is not a value
    plausibility.py  a guard for values with no label to anchor them
    passes.py        the two reading passes
    context.py       descriptive fields for the card, never compared
"""
from __future__ import annotations

from .aliases import FIELDS, LABEL_RULES, label_to_field, normalize_label
from .context import CONTEXT_RULES, extract_context
from .model import Extracted, FieldSet
from .passes import extract_fields
from .placeholders import is_placeholder
from .plausibility import plausible

__all__ = [
    "FIELDS", "LABEL_RULES", "CONTEXT_RULES",
    "label_to_field", "normalize_label",
    "Extracted", "FieldSet",
    "extract_fields", "extract_context",
    "is_placeholder", "plausible",
]
