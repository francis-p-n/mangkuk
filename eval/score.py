#!/usr/bin/env python3
"""Score a submission against the organizers' ground truth.

    python eval/score.py --truth path/to/ground_truth.json
    python eval/score.py --truth gt.json --submission out/alt/submission.json
    python eval/score.py --truth gt.json --compare out/submission.json out/alt/submission.json

The bundle README states the weighting as 50% end-to-end (defects caught all
the way through) + 30% Stage-1 macro-F1 + 20% Stage-3 defect-F1, with
NEEDS_REVIEW reported separately as a reliability axis. The exact formulas are
not published, so each component is computed here in the most defensible way
and labelled. Treat the headline as an estimate and the per-component numbers
as the useful part — they say what to fix.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdoc.classify import CATEGORIES   # noqa: E402
from sdoc.fields import FIELDS         # noqa: E402


def load(path: str | Path) -> dict:
    """Read a submission or ground-truth file, tolerating a few shapes."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):                       # [{email_id: ..., ...}]
        data = {r["email_id"]: r for r in data}
    for key in ("ground_truth", "labels", "submission", "results"):
        if isinstance(data, dict) and key in data and isinstance(data[key], dict):
            data = data[key]
            break
    return data


def field_of(record: dict, *names, default=None):
    for n in names:
        if n in record and record[n] is not None:
            return record[n]
    return default


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def macro_f1_categories(truth: dict, sub: dict, ids: list[str]) -> tuple[float, dict]:
    per: dict[str, dict] = {}
    for cat in CATEGORIES:
        tp = sum(1 for i in ids
                 if field_of(truth[i], "category") == cat
                 and field_of(sub.get(i, {}), "category") == cat)
        fp = sum(1 for i in ids
                 if field_of(truth[i], "category") != cat
                 and field_of(sub.get(i, {}), "category") == cat)
        fn = sum(1 for i in ids
                 if field_of(truth[i], "category") == cat
                 and field_of(sub.get(i, {}), "category") != cat)
        p, r, f = prf(tp, fp, fn)
        per[cat] = {"precision": p, "recall": r, "f1": f,
                    "support": sum(1 for i in ids if field_of(truth[i], "category") == cat)}
    present = [c for c in CATEGORIES if per[c]["support"]]
    macro = sum(per[c]["f1"] for c in present) / len(present) if present else 0.0
    return macro, per


def defect_field_f1(truth: dict, sub: dict, ids: list[str]) -> tuple[float, float, dict]:
    """F1 over (email, field) defect pairs. Returns (micro, macro, per-field)."""
    per: dict[str, dict] = {}
    tp_all = fp_all = fn_all = 0
    for name in FIELDS:
        tp = fp = fn = 0
        for i in ids:
            in_truth = name in (field_of(truth[i], "defect_fields", default=[]) or [])
            in_sub = name in (field_of(sub.get(i, {}), "defect_fields", default=[]) or [])
            tp += in_truth and in_sub
            fp += (not in_truth) and in_sub
            fn += in_truth and (not in_sub)
        p, r, f = prf(tp, fp, fn)
        per[name] = {"precision": p, "recall": r, "f1": f, "support": tp + fn,
                     "tp": tp, "fp": fp, "fn": fn}
        tp_all, fp_all, fn_all = tp_all + tp, fp_all + fp, fn_all + fn
    scored = [n for n in FIELDS if per[n]["support"]]
    macro = sum(per[n]["f1"] for n in scored) / len(scored) if scored else 0.0
    micro = prf(tp_all, fp_all, fn_all)[2]
    return micro, macro, per


def end_to_end(truth: dict, sub: dict, ids: list[str]) -> dict:
    """Defects caught all the way through: classified right, then flagged."""
    defective = [i for i in ids if field_of(truth[i], "status") == "MISMATCH"]
    caught = exact = 0
    lost_at_classify = lost_at_compare = 0
    for i in defective:
        got = sub.get(i, {})
        right_category = field_of(got, "category") == field_of(truth[i], "category")
        flagged = field_of(got, "status") == "MISMATCH"
        if right_category and flagged:
            caught += 1
            if sorted(field_of(got, "defect_fields", default=[]) or []) == \
               sorted(field_of(truth[i], "defect_fields", default=[]) or []):
                exact += 1
        elif not right_category:
            lost_at_classify += 1
        else:
            lost_at_compare += 1

    # False alarms: clean drafts reported as defective.
    clean = [i for i in ids if field_of(truth[i], "status") == "OK"
             and field_of(truth[i], "category") == "BL_COMPARISON"]
    false_alarms = sum(1 for i in clean
                       if field_of(sub.get(i, {}), "status") == "MISMATCH")
    return {
        "defective": len(defective),
        "caught": caught,
        "exact_fields": exact,
        "rate": caught / len(defective) if defective else 0.0,
        "exact_rate": exact / len(defective) if defective else 0.0,
        "lost_at_classify": lost_at_classify,
        "lost_at_compare": lost_at_compare,
        "clean": len(clean),
        "false_alarms": false_alarms,
    }


def review_axis(truth: dict, sub: dict, ids: list[str]) -> dict:
    t = [i for i in ids if field_of(truth[i], "status") == "NEEDS_REVIEW"]
    s = [i for i in ids if field_of(sub.get(i, {}), "status") == "NEEDS_REVIEW"]
    both = set(t) & set(s)
    reason_match = sum(
        1 for i in both
        if field_of(truth[i], "review_reason") == field_of(sub[i], "review_reason")
    )
    p, r, f = prf(len(both), len(set(s) - set(t)), len(set(t) - set(s)))
    return {"truth": len(t), "reported": len(s), "agreed": len(both),
            "reason_match": reason_match, "precision": p, "recall": r, "f1": f}


def report(name: str, truth: dict, sub: dict, verbose: bool) -> float:
    ids = sorted(set(truth) & set(sub))
    missing = set(truth) - set(sub)

    print("=" * 70)
    print(f"{name}   ({len(ids)} scored" + (f", {len(missing)} MISSING" if missing else "") + ")")
    print("=" * 70)

    macro, per_cat = macro_f1_categories(truth, sub, ids)
    micro_def, macro_def, per_field = defect_field_f1(truth, sub, ids)
    e2e = end_to_end(truth, sub, ids)
    rev = review_axis(truth, sub, ids)

    exact = sum(1 for i in ids if field_of(truth[i], "category") == field_of(sub[i], "category"))
    print(f"\nstage 1 - category      accuracy {exact}/{len(ids)} = {exact / len(ids):.1%}"
          f"   macro-F1 {macro:.4f}")
    print(f"{'category':<16}{'P':>8}{'R':>8}{'F1':>8}{'support':>9}")
    for cat in CATEGORIES:
        c = per_cat[cat]
        print(f"  {cat:<14}{c['precision']:>8.3f}{c['recall']:>8.3f}"
              f"{c['f1']:>8.3f}{c['support']:>9}")

    print(f"\nstage 3 - defect fields   micro-F1 {micro_def:.4f}   macro-F1 {macro_def:.4f}")
    print(f"{'field':<20}{'P':>8}{'R':>8}{'F1':>8}{'tp':>5}{'fp':>5}{'fn':>5}")
    for name_ in FIELDS:
        f = per_field[name_]
        print(f"  {name_:<18}{f['precision']:>8.3f}{f['recall']:>8.3f}"
              f"{f['f1']:>8.3f}{f['tp']:>5}{f['fp']:>5}{f['fn']:>5}")

    print(f"\nend to end")
    print(f"  defective drafts in truth : {e2e['defective']}")
    print(f"  caught                    : {e2e['caught']}  ({e2e['rate']:.1%})")
    print(f"  caught with exact fields  : {e2e['exact_fields']}  ({e2e['exact_rate']:.1%})")
    print(f"  lost at classification    : {e2e['lost_at_classify']}")
    print(f"  lost at comparison        : {e2e['lost_at_compare']}")
    print(f"  false alarms on clean     : {e2e['false_alarms']} of {e2e['clean']}")

    print(f"\nneeds-review reliability (reported separately)")
    print(f"  truth {rev['truth']}, reported {rev['reported']}, agreed {rev['agreed']}"
          f"  F1 {rev['f1']:.3f}   reason matched on {rev['reason_match']}/{rev['agreed']}")

    headline = 0.50 * e2e["rate"] + 0.30 * macro + 0.20 * micro_def
    print(f"\nestimated final score: 0.50*{e2e['rate']:.4f} + 0.30*{macro:.4f}"
          f" + 0.20*{micro_def:.4f} = {headline:.4f}")

    if verbose:
        wrong = [(i, field_of(truth[i], "category"), field_of(sub[i], "category"))
                 for i in ids
                 if field_of(truth[i], "category") != field_of(sub[i], "category")]
        if wrong:
            print(f"\nmisclassified ({len(wrong)}) - most common confusions:")
            for (t, s), n in collections.Counter((t, s) for _, t, s in wrong).most_common(10):
                print(f"  {n:4}  truth {t:<15} -> said {s}")
            print("  examples:")
            for i, t, s in wrong[:12]:
                print(f"    {i}: {t} -> {s}")

        status_wrong = [(i, field_of(truth[i], "status"), field_of(sub[i], "status"))
                        for i in ids
                        if field_of(truth[i], "category") == "BL_COMPARISON"
                        and field_of(truth[i], "status") != field_of(sub[i], "status")]
        if status_wrong:
            print(f"\nwrong verdict on a comparison ({len(status_wrong)}):")
            for i, t, s in status_wrong[:20]:
                print(f"    {i}: truth {t:<13} -> said {s}")
    return headline


def main() -> int:
    ap = argparse.ArgumentParser(description="score against ground truth")
    ap.add_argument("--truth", required=True)
    ap.add_argument("--submission", default="out/submission.json")
    ap.add_argument("--compare", nargs="*", default=None,
                    help="score several submissions and rank them")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    truth = load(args.truth)
    print(f"ground truth: {len(truth)} labelled emails")
    by_cat = collections.Counter(field_of(r, "category") for r in truth.values())
    by_status = collections.Counter(
        field_of(r, "status") for r in truth.values()
        if field_of(r, "category") == "BL_COMPARISON")
    print(f"  categories: {dict(by_cat)}")
    print(f"  comparison outcomes: {dict(by_status)}\n")

    paths = args.compare or [args.submission]
    scores = {p: report(p, truth, load(p), not args.quiet) for p in paths}

    if len(scores) > 1:
        print("=" * 70)
        print("ranking")
        for p, s in sorted(scores.items(), key=lambda kv: -kv[1]):
            print(f"  {s:.4f}  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
