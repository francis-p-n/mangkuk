"""Turn two documents into a verdict a person can act on."""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from .documents import Document
from .fields import FIELDS, FieldSet, extract_fields
from .normalize import values_agree


@dataclass
class FieldComparison:
    field: str
    si_value: str | None
    bl_value: str | None
    agree: bool | None          # None = undecidable
    si_label: str = ""
    bl_label: str = ""
    si_line: int = 0
    bl_line: int = 0

    @property
    def is_defect(self) -> bool:
        return self.agree is False


@dataclass
class Verdict:
    status: str                                    # OK | MISMATCH | NEEDS_REVIEW
    review_reason: str | None = None
    defect_fields: list[str] = dc_field(default_factory=list)
    comparisons: list[FieldComparison] = dc_field(default_factory=list)
    note: str = ""

    @property
    def has_defect(self) -> bool:
        return self.status == "MISMATCH"


def _blocked(si: Document | None, bl: Document | None) -> str | None:
    """Reasons we cannot compare at all, most specific first."""
    if si is None or bl is None:
        return "missing_attachment"
    if not si.ok or not bl.ok:
        return "unreadable"
    if not si.type_matches_role or not bl.type_matches_role:
        return "wrong_doc_type"
    return None


def compare_documents(si: Document | None, bl: Document | None, resolver=None) -> Verdict:
    """Compare two documents.

    `resolver`, when supplied, gets one chance to find fields the deterministic
    parsers missed — before anything is escalated. Whatever it finds is treated
    exactly like a parsed field from here on: it goes through the same
    normalization and the same comparator.
    """
    blocker = _blocked(si, bl)
    if blocker:
        # Written for the person who has to act on it, not for a log file.
        detail = {
            "missing_attachment": "one of the two documents was not attached",
            "unreadable": "an attachment could not be opened",
            "wrong_doc_type": "an attachment is not the document it claims to be",
        }[blocker]
        if blocker == "wrong_doc_type" and si and bl:
            bad = si if not si.type_matches_role else bl
            sent = bad.doc_type.value.lower().replace("_", " ")
            expected = "bill of lading" if bad.role == "BL" else "shipping instruction"
            article = "an" if sent[0] in "aeiou" else "a"
            detail = (f"the carrier sent {article} {sent} instead of a {expected}"
                      if bad.role == "BL"
                      else f"the {expected} attachment is actually {article} {sent}")
        return Verdict(status="NEEDS_REVIEW", review_reason=blocker, note=detail)

    si_fields, bl_fields = extract_fields(si.text), extract_fields(bl.text)

    if resolver is not None:
        if si_fields.missing:
            resolver.resolve(si.text, si_fields, "shipping instruction")
        if bl_fields.missing:
            resolver.resolve(bl.text, bl_fields, "draft bill of lading")

    return compare_fieldsets(si_fields, bl_fields)


def compare_fieldsets(si_fields: FieldSet, bl_fields: FieldSet) -> Verdict:
    comparisons: list[FieldComparison] = []
    defects: list[str] = []
    undecidable: list[str] = []

    for name in FIELDS:
        s, b = si_fields.get(name), bl_fields.get(name)
        agree = None if (s is None or b is None) else values_agree(name, s.value, b.value)
        comparisons.append(
            FieldComparison(
                field=name,
                si_value=s.value if s else None,
                bl_value=b.value if b else None,
                agree=agree,
                si_label=s.label if s else "",
                bl_label=b.label if b else "",
                si_line=s.line_no if s else 0,
                bl_line=b.line_no if b else 0,
            )
        )
        if agree is False:
            defects.append(name)
        elif agree is None:
            undecidable.append(name)

    # A confirmed conflict outranks an undecidable field: the defect is real and
    # actionable even if some other field could not be read. Escalating the whole
    # email in that case would bury a caught defect.
    if defects:
        return Verdict(status="MISMATCH", defect_fields=defects, comparisons=comparisons)
    if undecidable:
        return Verdict(
            status="NEEDS_REVIEW",
            review_reason="missing_value",
            comparisons=comparisons,
            note="could not read: " + ", ".join(f.replace("_", " ") for f in undecidable),
        )
    return Verdict(status="OK", comparisons=comparisons)
