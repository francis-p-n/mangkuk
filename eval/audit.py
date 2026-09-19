#!/usr/bin/env python3
"""Audit the run without ground truth.

Three questions this answers:
  1. Where is normalization doing the deciding? Every OK field whose raw strings
     differ is a place we could be wrong, so list them for a human to eyeball.
  2. What did the rules abstain on? Low-confidence classifications are the
     residue an LLM stage should own.
  3. Did any label in the corpus go unmapped that looks like one of the seven?
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdoc.classify import classify                              # noqa: E402
from sdoc.documents import extract                              # noqa: E402
from sdoc.fields import label_to_field, normalize_label         # noqa: E402
from sdoc.mailsource import BundleMailSource                    # noqa: E402
from sdoc.normalize import _clean                               # noqa: E402
from sdoc.pipeline import run                                   # noqa: E402


def main() -> int:
    src = BundleMailSource(ROOT / "data")
    emails = src.emails()
    results = run(src)
    by_id = {r.email_id: r for r in results}

    print("=" * 66)
    print("1. NORMALIZATION SENSITIVITY  (agreements that needed normalizing)")
    print("=" * 66)
    buckets = collections.Counter()
    examples: dict[str, list[tuple[str, str, str]]] = collections.defaultdict(list)
    for r in results:
        for c in r.comparisons:
            if c["agree"] is not True:
                continue
            si, bl = c["si_value"] or "", c["bl_value"] or ""
            if si == bl:
                buckets["identical strings"] += 1
            elif _clean(si) == _clean(bl):
                buckets["case/punctuation only"] += 1
            else:
                buckets["normalization decided"] += 1
                examples[c["field"]].append((r.email_id, si, bl))
    total_agree = sum(buckets.values())
    for k, n in buckets.most_common():
        print(f"  {n:5}  {n / total_agree:6.1%}  {k}")
    print("\n  cases where normalization decided agreement (audit these):")
    for field, rows in sorted(examples.items()):
        print(f"    {field}  ({len(rows)})")
        for eid, si, bl in rows[:3]:
            print(f"      {eid}: SI={si!r}")
            print(f"      {' ' * len(eid)}  BL={bl!r}")

    print()
    print("=" * 66)
    print("2. CLASSIFIER RULE COVERAGE  (what the rules abstained on)")
    print("=" * 66)
    rules = collections.Counter()
    weak: list[tuple[str, str]] = []
    for e in emails:
        c = classify(e.subject, e.body, e.domain, e.attachments)
        rules[(c.category, c.rule, c.confidence)] += 1
        if c.confidence < 0.7:
            weak.append((e.email_id, e.subject))
    for (cat, rule, conf), n in sorted(rules.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  conf={conf:.2f}  {cat:<15} {rule}")
    print(f"\n  low-confidence residue: {len(weak)} / {len(emails)} ({len(weak) / len(emails):.1%})")
    for eid, subj in weak[:8]:
        print(f"    {eid}: {subj[:70]}")

    print()
    print("=" * 66)
    print("3. UNMAPPED LABELS  (anything that should have been one of the seven)")
    print("=" * 66)
    unmapped = collections.Counter()
    for e in emails:
        for path in e.attachments:
            doc = extract(src, path)
            if not doc.ok:
                continue
            for line in doc.text.splitlines():
                if ":" not in line:
                    continue
                label = line.partition(":")[0]
                norm = normalize_label(label)
                if norm and label_to_field(label) is None:
                    unmapped[norm] += 1
    for label, n in unmapped.most_common(20):
        print(f"  {n:5}  {label}")

    print()
    print("=" * 66)
    print("4. OUTCOME SUMMARY")
    print("=" * 66)
    comps = [r for r in results if r.category == "BL_COMPARISON"]
    decided = [r for r in comps if r.status in ("OK", "MISMATCH")]
    print(f"  emails                : {len(results)}")
    print(f"  comparison requests   : {len(comps)}")
    print(f"  decided automatically : {len(decided)} ({len(decided) / len(comps):.1%})")
    print(f"  escalated to a human  : {len(comps) - len(decided)} ({1 - len(decided) / len(comps):.1%})")
    print(f"  drafts with a defect  : {sum(r.has_defect for r in comps)}")
    print(f"  defective / decided   : {sum(r.has_defect for r in comps) / len(decided):.1%}")

    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "audit.json").write_text(json.dumps({
        "agreement_buckets": dict(buckets),
        "low_confidence": len(weak),
        "unmapped_labels": dict(unmapped.most_common(30)),
        "comparison_requests": len(comps),
        "decided": len(decided),
        "defects": sum(r.has_defect for r in comps),
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
