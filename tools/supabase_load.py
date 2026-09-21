#!/usr/bin/env python3
"""Load a run into Supabase.

    python tools/supabase_load.py                    # the scrambled demo
    python tools/supabase_load.py --results out/results.json --real
    python tools/supabase_load.py --dry-run          # build and check, send nothing

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment or .env. The
service key bypasses row-level security, which is the point: the pipeline is
the only writer, and the anon key the site ships with can only read.

Defaults to `out/results-demo.json` and refuses the real bundle without
`--real`, for the same reason deploy.sh does - a Supabase table behind an
anon key is as public as an S3 bucket, and the real run carries consignee
names, addresses and OC numbers.

PostgREST over urllib rather than the supabase client: the whole exchange is
two POSTs, and the project already talks HTTP this way in agents/clients.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sdoc.labels import as_payload      # noqa: E402
from sdoc.severity import BANDS         # noqa: E402

BATCH = 100          # rows per request; 520 rows in 6 round trips


class LoadError(RuntimeError):
    """Something the operator has to fix, reported without a traceback."""


def load_env() -> tuple[str, str]:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        pass
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or ""
    if not url or not key:
        raise LoadError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set - see .env.example"
        )
    return url, key


def post(url: str, key: str, path: str, rows: list[dict], *,
         prefer: str = "return=minimal") -> None:
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60):
            return
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise LoadError(f"{path}: HTTP {exc.code} - {detail}") from exc
    except urllib.error.URLError as exc:
        raise LoadError(f"{path}: cannot reach {url} - {exc.reason}") from exc


def row_of(rec: dict, run_id: str) -> dict:
    """One results row. Absent is null, not empty string."""
    def s(key: str):
        v = rec.get(key)
        return v if isinstance(v, str) and v.strip() else None

    return {
        "email_id": rec["email_id"],
        "run_id": run_id,
        "category": rec.get("category") or "GENERAL",
        "rule": s("rule"),
        "status": rec.get("status") or "OK",
        "review_reason": rec.get("review_reason"),
        "has_defect": bool(rec.get("has_defect")),
        "defect_fields": rec.get("defect_fields") or [],
        "subject": s("subject"),
        "sender": s("sender"),
        "oc_number": s("oc_number"),
        "booking_ref": s("booking_ref"),
        "note": s("note"),
        "severity": rec.get("severity"),
        "severity_field": rec.get("severity_field"),
        "severity_reason": s("severity_reason"),
        "documents": rec.get("documents") or [],
        "comparisons": rec.get("comparisons") or [],
        "shipment": rec.get("shipment") or {},
    }


def check(rows: list[dict]) -> list[str]:
    """Catch locally what the table's constraints would reject remotely.

    A rejected batch tells you a row was wrong somewhere in a hundred; this
    tells you which one, before anything is sent.
    """
    problems = []
    for r in rows:
        eid = r["email_id"]
        mismatch = r["status"] == "MISMATCH"
        if r["has_defect"] != mismatch:
            problems.append(f"{eid}: has_defect={r['has_defect']} but status={r['status']}")
        if mismatch and not r["defect_fields"]:
            problems.append(f"{eid}: MISMATCH names no defect_fields")
        if not mismatch and r["defect_fields"]:
            problems.append(f"{eid}: defect_fields set on {r['status']}")
        if (r["status"] == "NEEDS_REVIEW") != (r["review_reason"] is not None):
            problems.append(f"{eid}: review_reason must be set iff NEEDS_REVIEW")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=str(ROOT / "out" / "results-demo.json"))
    ap.add_argument("--real", action="store_true",
                    help="allow loading a run that is not the scrambled demo")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the rows and check them, send nothing")
    args = ap.parse_args()

    path = Path(args.results)
    if "demo" not in path.name and not args.real:
        print(f"{path.name} is not the scrambled build.\n"
              f"The table is readable by the anon key the site ships with, so "
              f"this publishes\nevery consignee name and OC number in it. Pass "
              f"--real if that is what you want.")
        return 64

    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"cannot read {path}: {exc}")
        return 66
    except json.JSONDecodeError as exc:
        print(f"{path} is not valid JSON: {exc}")
        return 65

    run_id = str(uuid.uuid4())
    rows = [row_of(r, run_id) for r in records]

    problems = check(rows)
    if problems:
        print(f"{len(problems)} row(s) contradict themselves and would be "
              f"rejected by the table:")
        for p in problems[:10]:
            print(f"  {p}")
        return 65

    # Counted the way ui/build.py counts, over comparison requests rather than
    # over rows that ended up with a comparison table. The two differ by the
    # requests whose attachment never arrived, and a headline that disagrees
    # with the existing site would be read as the new stack losing fifteen
    # shipments.
    comparisons = [r for r in rows if r["category"] == "BL_COMPARISON"]
    totals = {
        "emails": len(rows),
        "comparisons": len(comparisons),
        "mismatch": sum(r["status"] == "MISMATCH" for r in comparisons),
        "review": sum(r["status"] == "NEEDS_REVIEW" for r in comparisons),
        "ok": sum(r["status"] == "OK" for r in comparisons),
    }

    print(f"{path.name}: {len(rows)} rows, all self-consistent")
    print(f"  {totals}")

    if args.dry_run:
        print("\ndry run - nothing sent")
        return 0

    try:
        url, key = load_env()
        post(url, key, "runs", [{
            "id": run_id, "source": path.name, "totals": totals,
            "labels": as_payload(),
            "bands": [{"name": n, "consequence": c} for n, _, c in BANDS],
            "severity": {
                name: sum(r["severity"] == name for r in comparisons)
                for name, _, _ in BANDS
            },
            "is_current": False,
        }])
        for i in range(0, len(rows), BATCH):
            post(url, key, "results", rows[i:i + BATCH])
            print(f"  sent {min(i + BATCH, len(rows))}/{len(rows)}")

        # Flip last: until this, the site still serves the previous run, and
        # a load that dies halfway leaves nothing half-shown.
        req = urllib.request.Request(
            f"{url}/rest/v1/runs?id=eq.{run_id}",
            data=json.dumps({"is_current": True}).encode(),
            method="PATCH",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     "Prefer": "return=minimal"},
        )
        with urllib.request.urlopen(req, timeout=60):
            pass
    except LoadError as exc:
        print(f"\n{exc}")
        return 70

    print(f"\nloaded, and now current: run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
