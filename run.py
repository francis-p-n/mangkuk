#!/usr/bin/env python3
"""CLI entry point.

    python run.py                      # run over data/, write out/
    python run.py --source http://host:8080
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from sdoc.mailsource import open_source          # noqa: E402
from sdoc.pipeline import run, write_outputs      # noqa: E402
from sdoc.validate import validate                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="SDOC verification pipeline")
    ap.add_argument("--source", default="data", help="bundle folder or server URL")
    ap.add_argument("--out", default="out", help="output folder")
    ap.add_argument("--sample", default="data/sample_submission.json")
    args = ap.parse_args()

    results = run(open_source(args.source))
    sub_path, res_path = write_outputs(results, args.out)

    cats = collections.Counter(r.category for r in results)
    comps = [r for r in results if r.category == "BL_COMPARISON"]
    stats = collections.Counter(r.status for r in comps)
    reasons = collections.Counter(r.review_reason for r in comps if r.review_reason)
    defects = collections.Counter(f for r in comps for f in r.defect_fields)

    print(f"processed {len(results)} emails\n")
    print("categories")
    for c, n in cats.most_common():
        print(f"  {n:4}  {c}")
    print(f"\ncomparison outcomes ({len(comps)} emails)")
    for s, n in stats.most_common():
        print(f"  {n:4}  {s}")
    if reasons:
        print("\nreview reasons")
        for r, n in reasons.most_common():
            print(f"  {n:4}  {r}")
    if defects:
        print("\ndefect fields")
        for f, n in defects.most_common():
            print(f"  {n:4}  {f}")

    problems = validate(json.loads(sub_path.read_text(encoding="utf-8")), args.sample)
    print()
    if problems:
        print(f"submission INVALID — {len(problems)} problem(s)")
        for p in problems[:15]:
            print("  -", p)
        return 1
    print(f"submission valid -> {sub_path}")
    print(f"results          -> {res_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
