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

# Load ROOT/.env into os.environ so API keys need not be exported by hand.
# Optional: without python-dotenv the real environment still works as before.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from sdoc.agents import (                      # noqa: E402
    MAX_RETRIES, AgentStats, AgentUnavailable, FieldResolver, TriageAgent,
    make_client,
)
from sdoc.learned import Overrides                # noqa: E402
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
        "--submit", action="store_true",
        help="POST the submission to the server named by --source and print "
             "its reply. The only step that sends anything anywhere, so it "
             "never happens unless asked for.",
    )
    ap.add_argument(
        "--learned", metavar="FILE",
        help="apply the desk's own corrections from an overrides file "
             "(see sdoc/learned.py); off by default, so the scored run stays "
             "reproducible from the repo alone",
    )
    ap.add_argument(
        "--agent", choices=("off", "bedrock", "anthropic", "gemini"), default="off",
        help="run the LLM recovery stage before escalating (default: off)",
    )
    args = ap.parse_args()

    try:
        learned = Overrides.load(args.learned)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.learned}: {exc}")
        return 2
    if learned:
        hushed = len(learned.suppressions)
        tail = f", {hushed} of which stop a flag being raised" if hushed else ""
        print(f"applying {len(learned)} correction(s) the desk recorded{tail}\n")

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
        # 72 sequential calls against the supplied bundle, and a free tier
        # will throttle most of a minute away. Without a line per call the
        # run looks hung, and the first thing anyone does to a hung run is
        # kill it.
        agent_stats.progress = lambda line: print(f"  {line}", flush=True)
        print(f"agent stage: {args.agent}, up to {MAX_RETRIES} retries per call\n")

    source = open_source(args.source)

    # Validate against the shape the server expects, not a local copy that may
    # describe a different set of emails than the one being scored.
    sample = args.sample
    if hasattr(source, "sample_submission"):
        try:
            sample = source.sample_submission()
            print(f"sample submission from the server: {len(sample)} emails\n")
        except Exception as exc:
            print(f"could not fetch the sample from the server ({exc});")
            print(f"falling back to {args.sample}\n")

    try:
        results = run(source, args.chase_as_comparison, resolver, triage, learned)
    except OSError as exc:
        # Losing the listing is fatal - there is nothing to process - but it
        # is an infrastructure problem, and a stack trace says that badly.
        print(f"could not read the mailbox: {exc}")
        print("check the server is up and --source is right.")
        return 2
    sub_path, res_path = write_outputs(results, args.out)

    # A document we never fetched is not a document we could not read, and a
    # run that lost attachments must not be mistaken for a clean one.
    unfetched = [(r.email_id, d["path"]) for r in results for d in r.documents
                 if d.get("error") == "fetch_failed"]

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

        # The distinction the whole retry layer exists to preserve: a model
        # that found nothing and a model that was never reached look the
        # same in the output and need opposite responses.
        if agent_stats.incomplete:
            missed = agent_stats.rate_limited + agent_stats.failed
            print(f"\n  {missed} of {agent_stats.calls} calls never got an answer"
                  f" ({agent_stats.rate_limited} rate limited,"
                  f" {agent_stats.failed} failed).")
            print("  Those emails fell back to the rules, so the submission is")
            print("  complete - but the agent stage is not, and nothing here says")
            print("  anything about how well the prompts work. Slow the run down")
            print("  (SDOC_MAX_RETRIES) or use a key with a higher limit, then")
            print("  judge the prompts on a run that was actually answered.")
        for note in agent_stats.notes[:5]:
            print(f"  note: {note}")

    if unfetched:
        print(f"\n{len(unfetched)} attachment(s) never arrived. Those checks are "
              "reported as escalations, but the run is incomplete:\nany defect in "
              "those documents was never seen. Re-run before trusting this.")
        for email_id, path in unfetched[:10]:
            print(f"  {email_id}  {path}")
        if len(unfetched) > 10:
            print(f"  ... and {len(unfetched) - 10} more")

    problems = validate(json.loads(sub_path.read_text(encoding="utf-8")), sample)
    print()
    if problems:
        print(f"submission INVALID — {len(problems)} problem(s)")
        for p in problems[:15]:
            print("  -", p)
        return 1
    print(f"submission valid -> {sub_path}")
    print(f"results          -> {res_path}")

    if args.submit:
        if not hasattr(source, "submit"):
            print("\n--submit needs an HTTP source; point --source at the server")
            return 2
        print("\nsubmitting...")
        try:
            reply = source.submit(json.loads(sub_path.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"the server refused it: {type(exc).__name__}: {exc}")
            return 1
        print(json.dumps(reply, indent=2))

    # A run that lost attachments exits non-zero, so a script cannot mistake
    # it for a clean one even though the submission is structurally valid.
    return 3 if unfetched else 0


if __name__ == "__main__":
    raise SystemExit(main())
