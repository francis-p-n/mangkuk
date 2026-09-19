"""Validate a submission before it ever reaches the scorer."""
from __future__ import annotations

import json
from pathlib import Path

from .classify import CATEGORIES

STATUSES = {"OK", "MISMATCH", "NEEDS_REVIEW"}
REASONS = {"wrong_doc_type", "missing_attachment", "unreadable", "missing_value"}
REQUIRED_KEYS = {"category", "status", "review_reason", "defect_fields", "has_defect"}


def validate(submission: dict, sample_path: str | Path) -> list[str]:
    """Return a list of problems. Empty list means the file is submittable."""
    problems: list[str] = []
    sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))

    missing = set(sample) - set(submission)
    extra = set(submission) - set(sample)
    if missing:
        problems.append(f"{len(missing)} email_ids missing, e.g. {sorted(missing)[:3]}")
    if extra:
        problems.append(f"{len(extra)} unexpected email_ids, e.g. {sorted(extra)[:3]}")

    for eid, rec in submission.items():
        where = f"{eid}:"
        if set(rec) != REQUIRED_KEYS:
            problems.append(f"{where} keys {sorted(set(rec) ^ REQUIRED_KEYS)} differ from the sample")
            continue
        if rec["category"] not in CATEGORIES:
            problems.append(f"{where} bad category {rec['category']!r}")
        if rec["status"] not in STATUSES:
            problems.append(f"{where} bad status {rec['status']!r}")
        if rec["review_reason"] is not None and rec["review_reason"] not in REASONS:
            problems.append(f"{where} bad review_reason {rec['review_reason']!r}")

        is_mismatch = rec["status"] == "MISMATCH"
        if rec["has_defect"] != is_mismatch:
            problems.append(f"{where} has_defect={rec['has_defect']} contradicts status={rec['status']}")
        if is_mismatch and not rec["defect_fields"]:
            problems.append(f"{where} MISMATCH with no defect_fields")
        if not is_mismatch and rec["defect_fields"]:
            problems.append(f"{where} defect_fields set on a non-MISMATCH")
        if (rec["status"] == "NEEDS_REVIEW") != (rec["review_reason"] is not None):
            problems.append(f"{where} review_reason must be set iff status is NEEDS_REVIEW")

    return problems
