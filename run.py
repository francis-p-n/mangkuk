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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from sdoc.agents import (                      # noqa: E402
    AgentStats, AgentUnavailable, FieldResolver, TriageAgent, make_client,
)
from sdoc.mailsource import open_source          # noqa: E402
from sdoc.pipeline import run, write_outputs      # noqa: E402
from sdoc.validate import validate                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="SDOC verification pipeline")
    ap.add_argument("--source", default=str(ROOT / "data"), help="bundle folder or server URL")
    ap.add_argument("--out", default=str(ROOT / "out"), help="output folder")
    ap.add_argument("--sample", default=str(ROOT / "data" / "sample_submission.json"))
    ap.add_argument(
        "--chase-as-comparison", action="store_true",
        help="treat 'please send the draft BL for checking' emails as comparison "
             "requests with a missing attachment (see docs/assumptions.md)",
    )
    ap.add_argument(
        "--agent", choices=("off", "bedrock", "anthropic"), default="off",
        help="run the LLM recovery stage before escalating (default: off)",
    )
    args = ap.parse_args()

    agent_stats = AgentStats()
    resolver = triage = None
    if args.agent != "off":
        try:
            client = make_client(args.agent)
        except AgentUnavailable as exc:
            print(f"cannot start the agent stage: {exc}")
            print("the deterministic pipeline still runs with --agent off")
            return 2
        resolver = FieldResolver(client, agent_stats)
        triage = TriageAgent(client, agent_stats)
        print(f"agent stage: {args.agent}\n")

    results = run(open_source(args.source), args.chase_as_comparison, resolver, triage)
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

    if args.agent != "off":
        print("\nagent recovery")
        print(f"  {agent_stats.resolver_calls:4}  documents sent to the resolver")
        print(f"  {agent_stats.fields_requested:4}  fields it was asked to find")
        print(f"  {agent_stats.fields_returned:4}  values it proposed")
        print(f"  {agent_stats.fields_accepted:4}  accepted (grounded in the document)")
        print(f"  {agent_stats.rejected_ungrounded:4}  rejected - quote not in the document")
        print(f"  {agent_stats.rejected_implausible:4}  rejected - implausible for the field")
        print(f"  {agent_stats.triage_calls:4}  classifications requested"
              f" / {agent_stats.triage_accepted} accepted")
        for note in agent_stats.notes[:5]:
            print(f"  note: {note}")

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
