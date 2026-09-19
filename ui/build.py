#!/usr/bin/env python3
"""Inline the run's results into a single self-contained page.

No server, no build tooling, no fetch. The output opens by double-click and
uploads to S3 unchanged, which is one fewer thing to fail during a demo.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEEP = (
    "email_id", "subject", "sender", "status", "review_reason", "has_defect",
    "defect_fields", "note", "oc_number", "booking_ref", "shipment", "comparisons",
)


def slim(record: dict) -> dict:
    out = {k: record.get(k) for k in KEEP}
    out["comparisons"] = [
        {k: c[k] for k in ("field", "si_value", "bl_value", "agree",
                           "si_label", "bl_label", "si_line", "bl_line")}
        for c in record.get("comparisons", [])
    ]
    return out


def main() -> int:
    results_path = ROOT / "out" / "results.json"
    if not results_path.exists():
        print("out/results.json not found - run `python run.py` first")
        return 1

    results = json.loads(results_path.read_text(encoding="utf-8"))
    comparisons = [r for r in results if r["category"] == "BL_COMPARISON"]
    order = {"MISMATCH": 0, "NEEDS_REVIEW": 1, "OK": 2}
    comparisons.sort(key=lambda r: (order[r["status"]], r["email_id"]))

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "totals": {
            "emails": len(results),
            "comparisons": len(comparisons),
            "mismatch": sum(r["status"] == "MISMATCH" for r in comparisons),
            "review": sum(r["status"] == "NEEDS_REVIEW" for r in comparisons),
            "ok": sum(r["status"] == "OK" for r in comparisons),
        },
        "shipments": [slim(r) for r in comparisons],
    }

    template = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    # </script> inside the JSON would close the host tag early.
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<" + chr(92) + "/")
    page = template.replace("__SDOC_DATA__", blob)

    dest = ROOT / "out" / "ui"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.html").write_text(page, encoding="utf-8")
    size = (dest / "index.html").stat().st_size
    print(f"wrote {dest / 'index.html'}  ({size / 1024:.0f} KB, {len(payload['shipments'])} shipments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
