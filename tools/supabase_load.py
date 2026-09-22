#!/usr/bin/env python3
"""Load a run into Supabase.

    python tools/supabase_load.py                    # the scrambled demo
    python tools/supabase_load.py --results out/results.json --real
    python tools/supabase_load.py --dry-run          # build and check, send nothing

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment or .env. The
service key bypasses row-level security, which is the point: the pipeline is
the only writer, and the anon key the site ships with can only read.

Defaults to `out/results-demo.json` and refuses the real bundle without
`--real`. The table is readable by the anon key the site ships in its own
JavaScript, so loading the real run publishes every consignee name, address
and OC number in it to anyone who opens the site.

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
    # Supabase renamed the write key: older projects issue a "service role
    # key", newer ones a "secret key". A project has one or the other, so both
    # names are read rather than making the operator translate.
    key = next((os.environ[n] for n in
                ("SUPABASE_SERVICE_KEY", "SUPABASE_SECRET_KEY",
                 "SUPABASE_SERVICE_ROLE_KEY")
                if os.environ.get(n)), "")
    if not url or not key:
        raise LoadError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_SECRET_KEY) "
            "must be set - see .env.example"
        )
    return url, key


# PostgREST's code for "you sent a column this table has not got". The
# schema is versioned in supabase/migrations/ and applied by hand in the SQL
# editor, so code reaches a project before a migration does - and a nightly
# reload should not fail because one nice-to-have column is not there yet.
UNKNOWN_COLUMN = "PGRST204"

# Columns the site can do without. `body` arrived in migration 0002 and only
# feeds the "read the original email" panel; web/lib/supabase.ts already
# drops it on the same error when reading.
OPTIONAL_COLUMNS = ("body",)


class MissingColumn(LoadError):
    """The table is older than this code. Which column, so it can be dropped."""

    def __init__(self, column: str, detail: str):
        super().__init__(detail)
        self.column = column


def missing_column(detail: str) -> str | None:
    if UNKNOWN_COLUMN not in detail:
        return None
    for column in OPTIONAL_COLUMNS:
        if f"'{column}' column" in detail:
            return column
    return None


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
        column = missing_column(detail)
        if column:
            raise MissingColumn(column, f"{path}: HTTP {exc.code} - {detail}")
        raise LoadError(f"{path}: HTTP {exc.code} - {detail}") from exc
    except urllib.error.URLError as exc:
        raise LoadError(f"{path}: cannot reach {url} - {exc.reason}") from exc


def patch(url: str, key: str, query: str, fields: dict) -> None:
    """PATCH rows matching a PostgREST filter. Errors read like post()'s."""
    req = urllib.request.Request(
        f"{url}/rest/v1/{query}",
        data=json.dumps(fields).encode("utf-8"),
        method="PATCH",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60):
            return
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise LoadError(f"{query}: HTTP {exc.code} - {detail}") from exc
    except urllib.error.URLError as exc:
        raise LoadError(f"{query}: cannot reach {url} - {exc.reason}") from exc


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
        "body": s("body"),
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

    # Counted over comparison requests, not over rows that ended up with a
    # comparison table. The two differ by the requests whose attachment never
    # arrived - fifteen of them - and counting the narrower set would quietly
    # drop those from every headline the site shows.
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
        # Retry without a column the table has not got, rather than failing
        # the whole load. Said out loud: a run missing the email text is
        # worth having, and silently publishing one is not.
        dropped: list[str] = []
        i = 0
        while i < len(rows):
            batch = rows[i:i + BATCH]
            try:
                # Upsert, because `results` keys on email_id alone: the table
                # holds one run's worth of rows at a time by design, so a
                # second load collides with the first on every row. Merging
                # duplicates makes a reload idempotent - each email keeps one
                # row, carrying the newest run's verdict and run_id - which is
                # what a demo that gets reloaded all week needs.
                post(url, key, "results", batch,
                     prefer="return=minimal,resolution=merge-duplicates")
            except MissingColumn as exc:
                print(f"  this project has no '{exc.column}' column - "
                      f"apply supabase/migrations/ to get it")
                print(f"  loading without it; the site reads round a missing "
                      f"'{exc.column}' already")
                dropped.append(exc.column)
                for row in rows:
                    row.pop(exc.column, None)
                continue          # same batch, one column lighter
            i += BATCH
            print(f"  sent {min(i, len(rows))}/{len(rows)}")

        if dropped:
            print(f"  note: loaded without {', '.join(dropped)}")

        # Flip last: until this, the site still serves the previous run, and
        # a load that dies halfway leaves nothing half-shown.
        #
        # Two steps, because `runs_one_current` is a unique index on
        # is_current where it is true - exactly one run may be current, so
        # the old one has to stand down before the new one can stand up.
        # Setting the new one first is a 409, which is what this did until a
        # project was loaded twice. Between the two there is a moment with no
        # current run, and the site shows its "nothing loaded yet" page for
        # that moment rather than a wrong verdict.
        patch(url, key, "runs?is_current=eq.true", {"is_current": False})
        patch(url, key, f"runs?id=eq.{run_id}", {"is_current": True})
    except LoadError as exc:
        print(f"\n{exc}")
        return 70

    print(f"\nloaded, and now current: run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
