"""Orchestration: inbox in, submission.json + results.json out.

Two outputs on purpose. `submission.json` is the narrow shape the scorer wants.
`results.json` is everything a human needs — evidence lines, shipment refs,
per-field comparisons — and is what the workspace UI reads.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field as dc_field
from pathlib import Path

from .classify import Classification, classify
from .compare import Verdict, compare_documents
from .documents import Document, extract
from .fields import FIELDS, extract_context, extract_fields
from .learned import Overrides
from .mailsource import Email, MailSource
from .places import PlaceBook, country_from_address
from .severity import assess
from .shipment import Refs, find_refs


@dataclass
class EmailResult:
    email_id: str
    category: str
    rule: str
    status: str = "OK"
    review_reason: str | None = None
    has_defect: bool = False
    defect_fields: list[str] = dc_field(default_factory=list)
    # context for the UI, ignored by the scorer
    subject: str = ""
    sender: str = ""
    # The message itself, so a clerk can read what was actually asked before
    # acting on a verdict about it. Carried for the UI only - the scorer never
    # sees it, and to_submission() does not include it.
    body: str = ""
    oc_number: str | None = None
    booking_ref: str | None = None
    note: str = ""
    # what the worst wrong field would cost, so a queue can be worked in order
    severity: str | None = None
    severity_field: str | None = None
    severity_reason: str = ""
    documents: list[dict] = dc_field(default_factory=list)
    comparisons: list[dict] = dc_field(default_factory=list)
    shipment: dict = dc_field(default_factory=dict)

    def to_submission(self) -> dict:
        return {
            "category": self.category,
            "status": self.status,
            "review_reason": self.review_reason,
            "defect_fields": list(self.defect_fields),
            "has_defect": self.has_defect,
        }


def _doc_summary(doc: Document | None, role: str) -> dict:
    if doc is None:
        return {"role": role, "present": False}
    return {
        "role": role,
        "present": True,
        "path": doc.path,
        "format": doc.fmt,
        "readable": doc.ok,
        "doc_type": doc.doc_type.value,
        "type_matches_role": doc.type_matches_role,
        "error": doc.error,
    }


def _shipment_facts(si: Document | None, bl: Document | None) -> dict:
    """Header facts for the shipment card, preferring the SI as the reference."""
    for doc in (si, bl):
        if doc is not None and doc.ok:
            fs = extract_fields(doc.text)
            facts = {
                name: (fs.get(name).value if fs.get(name) else None)
                for name in FIELDS
            }
            # The party's address sits on the continuation line under its name.
            consignee = fs.get("consignee")
            address = consignee.detail if consignee else ""
            return facts | extract_context(doc.text) | {
                "source": doc.role,
                "mode": "sea",
                "consignee_address": address or None,
                "consignee_country": country_from_address(address) or None,
            }
    return {}


CONFIDENCE_FLOOR = 0.7


def process_email(
    source: MailSource,
    email: Email,
    chase_as_comparison: bool = False,
    resolver=None,
    triage=None,
    learned: Overrides | None = None,
) -> EmailResult:
    cls = classify(
        email.subject, email.body, email.domain, email.attachments, chase_as_comparison
    )

    # The rules abstained. Hand it to the agent rather than defaulting.
    if triage is not None and cls.confidence < CONFIDENCE_FLOOR:
        decided = triage.classify(email.subject, email.body)
        if decided:
            cls = Classification(decided, f"agent_after_{cls.rule}", 0.75)
    refs: Refs = find_refs(email.subject, email.body)
    result = EmailResult(
        email_id=email.email_id,
        category=cls.category,
        rule=cls.rule,
        subject=email.subject,
        sender=email.sender,
        body=email.body,
        oc_number=refs.oc,
        booking_ref=refs.booking,
    )

    if cls.category != "BL_COMPARISON":
        return result

    si = bl = None
    for path in email.attachments:
        doc = extract(source, path)
        if doc.role == "SI":
            si = doc
        else:
            bl = doc

    verdict: Verdict = compare_documents(si, bl, resolver, learned)
    result.status = verdict.status
    result.review_reason = verdict.review_reason
    result.has_defect = verdict.has_defect
    result.defect_fields = verdict.defect_fields
    result.note = verdict.note
    worst = assess(verdict.defect_fields)
    if worst:
        result.severity = worst.band
        result.severity_field = worst.field
        result.severity_reason = worst.reason
    result.documents = [_doc_summary(si, "SI"), _doc_summary(bl, "BL")]
    result.comparisons = [asdict(c) for c in verdict.comparisons]
    result.shipment = _shipment_facts(si, bl)

    # Documents carry references the email subject may not.
    if not result.oc_number:
        doc_refs = find_refs(*(d.text for d in (si, bl) if d and d.ok))
        result.oc_number = result.oc_number or doc_refs.oc
        result.booking_ref = result.booking_ref or doc_refs.booking

    return result


def run(
    source: MailSource,
    chase_as_comparison: bool = False,
    resolver=None,
    triage=None,
    learned: Overrides | None = None,
) -> list[EmailResult]:
    results = [
        process_email(source, e, chase_as_comparison, resolver, triage, learned)
        for e in source.emails()
    ]
    settle_places(results)
    return results


def settle_places(results: list[EmailResult]) -> None:
    """Give every port one spelling, so a filter lists each destination once.

    Two passes: learn the UN/LOCODEs the documents do state, then apply them to
    the ports written without one.
    """
    book = PlaceBook()
    for r in results:
        for key in ("port_of_loading", "port_of_discharge"):
            book.learn(r.shipment.get(key) or "")

    for r in results:
        if not r.shipment:
            continue
        for key, prefix in (("port_of_loading", "loading"), ("port_of_discharge", "discharge")):
            place = book.canonical(r.shipment.get(key) or "")
            r.shipment[f"{prefix}_port"] = place["name"] or None
            r.shipment[f"{prefix}_city"] = place["city"] or None
            r.shipment[f"{prefix}_country"] = place["country"] or None
            r.shipment[f"{prefix}_locode"] = place["locode"] or None


def write_outputs(results: list[EmailResult], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    submission = {r.email_id: r.to_submission() for r in results}
    sub_path = out / "submission.json"
    sub_path.write_text(json.dumps(submission, indent=2), encoding="utf-8")

    res_path = out / "results.json"
    res_path.write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return sub_path, res_path
