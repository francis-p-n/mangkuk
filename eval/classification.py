#!/usr/bin/env python3
"""Is the classifier right? Not: how much of the corpus will it decide.

    python eval/classification.py              # the score, and every disagreement
    python eval/classification.py --confusion  # plus the confusion matrix
    python eval/classification.py --json       # machine-readable

WHAT WAS WRONG WITH THE OLD NUMBER

`eval/audit.py` reports the low-confidence residue: 59 of 520 emails that no
rule will decide. The rubric held that number down. It is a coverage figure,
and coverage is not accuracy - a rule can decide an email confidently and
wrongly, and nothing here noticed.

Demonstrated, not theorised: adding "documentation", "berthing" and "billing"
to the invoice phrase list refiles 55 berthing reports, RPA notifications and
a time-off request as invoice questions. Every one of the 432 tests still
passed, and the residue *improved* from 59 to 4. The harness scored a plainly
worse classifier as a better one.

WHAT THIS DOES INSTEAD

`eval/gold/clusters.json` holds a human label for each of the 33 templates the
corpus is written from, decided by reading one exemplar each (see
`eval/fingerprint.py` for how the templates are recovered). Expanding those 33
decisions over the corpus gives a label for all 520 emails, and this compares
the classifier against them: macro-F1, per-category precision and recall, and
every disagreement listed by name so it can be argued with.

TWO THINGS IT REFUSES TO DO

It will not score against a label nobody is sure of. Only rows at confidence
0.90 or above are used; anything below is reported as uncovered, which counts
against the measurement rather than against the classifier.

It will not let a judgement call flatter the result. Two templates are marked
contested - the 91 draft-chasers and the 23 missing-GR billing notes - because
the taxonomy has two boxes that genuinely fit. Those are scored on their own
line. The headline is the 406 emails where the label is a plain reading, and
the contested ones are reported beside it rather than folded in.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

from fingerprint import load as load_clusters      # noqa: E402
import sdoc.classify as classifier                 # noqa: E402
from sdoc.classify import CATEGORIES                # noqa: E402

GOLD = ROOT / "eval" / "gold" / "clusters.json"

# A label the reader was not sure of is not ground truth. This is the number
# the whole measurement rests on, so it is named rather than inlined.
SURE = 0.90


class GoldError(RuntimeError):
    """The labels and the corpus have come apart."""


def read_gold(path: Path = GOLD) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GoldError(f"cannot read {path.name}: {exc}") from exc
    return raw["labels"]


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)
    return precision, recall, f1


class Scored:
    """One comparison of the classifier against the gold labels."""

    def __init__(self, pairs: list[tuple[str, str, str]]):
        # (email_id, gold, predicted)
        self.pairs = pairs
        self.per: dict[str, dict] = {}
        for cat in CATEGORIES:
            tp = sum(1 for _, g, p in pairs if g == cat and p == cat)
            fp = sum(1 for _, g, p in pairs if g != cat and p == cat)
            fn = sum(1 for _, g, p in pairs if g == cat and p != cat)
            precision, recall, f1 = prf(tp, fp, fn)
            self.per[cat] = {
                "precision": precision, "recall": recall, "f1": f1,
                "support": sum(1 for _, g, _ in pairs if g == cat),
                "tp": tp, "fp": fp, "fn": fn,
            }
        present = [c for c in CATEGORIES if self.per[c]["support"]]
        self.macro_f1 = (sum(self.per[c]["f1"] for c in present) / len(present)
                         if present else 0.0)
        self.right = sum(1 for _, g, p in pairs if g == p)

    @property
    def total(self) -> int:
        return len(self.pairs)

    @property
    def accuracy(self) -> float:
        return self.right / self.total if self.total else 0.0

    @property
    def wrong(self) -> list[tuple[str, str, str]]:
        return [(e, g, p) for e, g, p in self.pairs if g != p]


def evaluate(source: str | Path | None = None) -> dict:
    """Score the shipped classifier against the gold labels."""
    gold = read_gold()
    clusters = load_clusters(source)

    missing = [c.id for c in clusters if c.id not in gold]
    if missing:
        raise GoldError(
            f"{len(missing)} template(s) have no label, so part of the corpus "
            f"cannot be scored: {missing[:4]}. Run eval/fingerprint.py and add "
            f"them to {GOLD.name} - a template that appears without anyone "
            f"deciding what it is must not be silently skipped."
        )

    impure = [c.id for c in clusters if not c.pure]
    if impure:
        raise GoldError(
            f"{len(impure)} template(s) no longer hold one kind of email "
            f"({impure[:4]}); one label for them would be wrong for some."
        )

    sure: list[tuple[str, str, str]] = []
    contested: list[tuple[str, str, str]] = []
    unsure: list[str] = []
    by_cluster: dict[str, dict] = {}

    for c in clusters:
        row = gold[c.id]
        label = row["label"]
        if label not in CATEGORIES:
            raise GoldError(f"template {c.id} is labelled {label!r}, which is "
                            f"not one of {CATEGORIES}")
        got = collections.Counter()
        for e in c.emails:
            # Through the module, not a bound name: eval/classifier_mutation.py
            # rewrites the rules in place and must be able to reach this call.
            predicted = classifier.classify(
                e.subject, e.body, e.domain, e.attachments)
            got[predicted.category] += 1
            triple = (e.email_id, label, predicted.category)
            if row.get("confidence", 0) < SURE:
                unsure.append(e.email_id)
            elif row.get("contested"):
                contested.append(triple)
            else:
                sure.append(triple)
        by_cluster[c.id] = {
            "size": c.size,
            "gold": label,
            "confidence": row.get("confidence"),
            "contested": bool(row.get("contested")),
            "exemplar": c.exemplar.email_id,
            "fingerprint": c.fingerprint,
            "predicted": dict(got),
            "agrees": got.get(label, 0),
        }

    # Consistency needs no labels at all, and it is the sharper instrument of
    # the two. Emails written from one template are one message; a classifier
    # that files them under two categories is being decided by something that
    # is not the message. In this corpus that something is the subject line -
    # the generator draws subjects and bodies independently for operational
    # mail, so "Submit SI & AED" sits on top of a berthing report - and a rule
    # that reads the subject over the body will split the template in half.
    split = {cid: c for cid, c in by_cluster.items() if len(c["predicted"]) > 1}
    inconsistent = sum(c["size"] for c in split.values())

    total = sum(c.size for c in clusters)
    return {
        "split": split,
        "inconsistent_emails": inconsistent,
        "corpus": total,
        "templates": len(clusters),
        "strict": Scored(sure),
        "contested": Scored(contested),
        "both": Scored(sure + contested),
        "uncovered": unsure,
        "clusters": by_cluster,
    }


def report(res: dict, show_confusion: bool = False) -> int:
    strict: Scored = res["strict"]
    cont: Scored = res["contested"]
    both: Scored = res["both"]
    total = res["corpus"]

    print("=" * 74)
    print("CLASSIFICATION ACCURACY  (against hand-labelled templates)")
    print("=" * 74)
    split = res["split"]
    print(f"  corpus                : {total} emails in {res['templates']} templates")
    print(f"  templates split across categories : {len(split)} "
          f"({res['inconsistent_emails']} emails)")
    print(f"  labelled at >= {SURE:.2f}  : {both.total} "
          f"({100 * both.total / total:.1f}% covered)")
    print(f"  of those, contested   : {cont.total}")
    print()
    print(f"  macro-F1              : {strict.macro_f1:.4f}   "
          f"(over {strict.total} plainly-labelled emails)")
    print(f"  accuracy              : {strict.accuracy:.4f}   "
          f"({strict.right}/{strict.total})")
    print(f"  disagreements         : {len(strict.wrong)}")
    print()
    print(f"  with contested rows   : macro-F1 {both.macro_f1:.4f}, "
          f"accuracy {both.accuracy:.4f} ({both.right}/{both.total})")
    print()

    print("  per category (plainly-labelled emails only)")
    print(f"    {'category':<16}{'P':>8}{'R':>8}{'F1':>8}{'n':>7}")
    for cat in CATEGORIES:
        row = strict.per[cat]
        if not row["support"] and not row["fp"]:
            continue
        print(f"    {cat:<16}{row['precision']:8.3f}{row['recall']:8.3f}"
              f"{row['f1']:8.3f}{row['support']:7}")

    if show_confusion:
        print("\n  confusion  (gold down, predicted across)")
        matrix = collections.Counter((g, p) for _, g, p in both.pairs)
        width = max(len(c) for c in CATEGORIES) + 1
        print("    " + " " * width + "".join(f"{c[:7]:>8}" for c in CATEGORIES))
        for g in CATEGORIES:
            cells = "".join(f"{matrix.get((g, p), 0):8}" for p in CATEGORIES)
            print(f"    {g:<{width}}{cells}")

    if strict.wrong:
        print(f"\n  DISAGREEMENTS  ({len(strict.wrong)})")
        grouped = collections.Counter((g, p) for _, g, p in strict.wrong)
        for (g, p), n in grouped.most_common():
            examples = [e for e, gg, pp in strict.wrong if gg == g and pp == p]
            print(f"    {n:4}  labelled {g}, classified {p}")
            print(f"          e.g. {', '.join(examples[:5])}")

    if cont.wrong:
        print(f"\n  CONTESTED, and the classifier takes the other reading "
              f"({len(cont.wrong)})")
        grouped = collections.Counter((g, p) for _, g, p in cont.wrong)
        for (g, p), n in grouped.most_common():
            print(f"    {n:4}  labelled {g}, classified {p}")

    if split:
        print()
        print(f"  TEMPLATES THE CLASSIFIER SPLITS  ({len(split)})")
        print("    One template is one message. A split means something other")
        print("    than the message decided it.")
        for cid, c in sorted(split.items(), key=lambda kv: -kv[1]["size"]):
            print(f"    {c['size']:4}  {c['predicted']}")
            print(f"          {c['fingerprint'][:66]}")

    if res["uncovered"]:
        print(f"\n  not scored - no label anyone was sure of: "
              f"{len(res['uncovered'])}")

    # One line a harness can read without guessing at the prose above it.
    print(f"SUMMARY templates={res['templates']} covered={both.total} "
          f"wrong={len(strict.wrong)} split={len(split)} "
          f"macro_f1={strict.macro_f1:.4f} contested={cont.total}")
    print()
    return 0 if not strict.wrong else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confusion", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--source", help="a bundle folder other than data/")
    args = ap.parse_args()

    try:
        res = evaluate(args.source)
    except GoldError as exc:
        print(f"cannot score the classifier: {exc}")
        return 2

    if args.json:
        strict: Scored = res["strict"]
        both: Scored = res["both"]
        print(json.dumps({
            "corpus": res["corpus"],
            "templates": res["templates"],
            "covered": both.total,
            "macro_f1": round(strict.macro_f1, 4),
            "accuracy": round(strict.accuracy, 4),
            "disagreements": len(strict.wrong),
            "contested": res["contested"].total,
            "split_templates": len(res["split"]),
            "inconsistent_emails": res["inconsistent_emails"],
            "per_category": {c: strict.per[c] for c in CATEGORIES},
            "wrong": [{"email": e, "gold": g, "got": p}
                      for e, g, p in strict.wrong],
        }, indent=2))
        return 0 if not strict.wrong else 1

    code = report(res, args.confusion)
    return code or (1 if res["split"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
