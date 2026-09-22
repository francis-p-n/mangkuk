#!/usr/bin/env python3
"""Break the classifier on purpose, and check the harness notices.

    python eval/classifier_mutation.py           # every mutant
    python eval/classifier_mutation.py -v        # with the numbers each one moved
    python eval/classifier_mutation.py --json

WHY

`eval/mutation.py` does this for the comparison stage: inject a known defect,
check it is caught. Nothing did it for the classifier, and that gap was not
theoretical. Broadening one invoice rule until 55 berthing reports and a
time-off request were filed as invoice questions left all 432 tests green and
*improved* the published residue figure from 59 to 4 - the harness scored a
plainly worse classifier as a better one.

A test suite that cannot fail on a bad classifier is not evidence about the
classifier. This measures that directly: fourteen realistic regressions, each
applied to the live rules, and the question asked of each is whether the
checks would have caught it.

HOW A MUTANT IS KILLED

Two signals, and they are independent:

  accuracy    - macro-F1 against the hand-labelled templates in
                eval/gold/clusters.json drops below 1.0.
  consistency - emails written from one template stop landing in one
                category. This needs no labels at all: a template is one
                message, so a split means something other than the message
                decided it.

The residue figure the rubric used to rely on is reported beside them, so the
difference between the old evidence and the new is on the page rather than in
a commit message.

WHAT THIS IS NOT

It is not proof the classifier is right - the labels are the evidence for
that. It is proof that if someone makes it wrong, something here goes red.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

import sdoc.classify as classifier                 # noqa: E402
from classification import evaluate                # noqa: E402
from sdoc.mailsource import BundleMailSource       # noqa: E402

# What the rules looked like before anything was done to them.
PRISTINE = {
    name: copy.deepcopy(getattr(classifier, name))
    for name in (
        "SPAM_DOMAINS", "SPAM_PHRASES", "COMPARISON_PHRASES", "CHASE_PHRASES",
        "SI_PHRASES", "SI_SUBJECTS", "INVOICE_PHRASES", "INVOICE_SUBJECTS",
        "OPERATIONAL_PHRASES",
    )
}

# The confidence floor the pipeline uses to decide what to hand an agent. The
# old rubric criterion counted everything below it.
FLOOR = 0.7


@dataclass
class Mutant:
    name: str
    what: str
    changes: dict = field(default_factory=dict)

    def apply(self) -> None:
        for name, value in self.changes.items():
            setattr(classifier, name, value)


def plus(name: str, *extra) -> tuple:
    return tuple(PRISTINE[name]) + extra


MUTANTS: list[Mutant] = [
    Mutant(
        "invoice rule broadened",
        "someone adds three plausible words to the invoice phrases",
        {"INVOICE_PHRASES": plus("INVOICE_PHRASES",
                                 "documentation", "berthing", "billing")},
    ),
    Mutant(
        "invoice rule broadened a little",
        "one plausible word rather than three - the change nobody reviews",
        {"INVOICE_PHRASES": plus("INVOICE_PHRASES", "charges")},
    ),
    Mutant(
        "operational rules deleted",
        "the positive rules for berthing reports and robot mail are removed",
        {"OPERATIONAL_PHRASES": ()},
    ),
    Mutant(
        "subject outranks body again",
        "the SI subject rule matches any subject with 'si' in it",
        {"SI_SUBJECTS": plus("SI_SUBJECTS", "si")},
    ),
    Mutant(
        "SI rule broadened",
        "'please find' is added to the instruction phrases",
        {"SI_PHRASES": plus("SI_PHRASES", "please find")},
    ),
    Mutant(
        "SI rules deleted",
        "shipping instructions stop being recognised",
        {"SI_PHRASES": (), "SI_SUBJECTS": ()},
    ),
    Mutant(
        "spam domains forgotten",
        "the known-bad sender list is emptied",
        {"SPAM_DOMAINS": set()},
    ),
    Mutant(
        "spam phrases forgotten",
        "the lottery and phishing wording is removed",
        {"SPAM_PHRASES": ()},
    ),
    Mutant(
        "spam detection deleted",
        "both legs at once - neither list alone is load-bearing any more",
        {"SPAM_DOMAINS": set(), "SPAM_PHRASES": ()},
    ),
    Mutant(
        "comparison phrases deleted",
        "only an attachment can make a comparison request now",
        {"COMPARISON_PHRASES": ()},
    ),
    Mutant(
        "chasers become instructions",
        "'draft bl' is added to the instruction phrases, catching the chasers",
        {"SI_PHRASES": plus("SI_PHRASES", "draft bl")},
    ),
    Mutant(
        "invoice rules narrowed",
        "all but the first invoice phrase are dropped",
        {"INVOICE_PHRASES": (PRISTINE["INVOICE_PHRASES"][0],),
         "INVOICE_SUBJECTS": ()},
    ),
    Mutant(
        "detention charges forgotten",
        "the one phrase that stopped 18 emails being decided by their subject",
        {"INVOICE_PHRASES": tuple(
            p for p in PRISTINE["INVOICE_PHRASES"] if p != "detention charges")},
    ),
    Mutant(
        "operational rule broadened",
        "'please find' makes everything an operational notice",
        {"OPERATIONAL_PHRASES": plus("OPERATIONAL_PHRASES", "please find")},
    ),
    Mutant(
        "everything is general",
        "every rule list is emptied - the classifier answers GENERAL always",
        {"SPAM_DOMAINS": set(), "SPAM_PHRASES": (), "COMPARISON_PHRASES": (),
         "CHASE_PHRASES": (), "SI_PHRASES": (), "SI_SUBJECTS": (),
         "INVOICE_PHRASES": (), "INVOICE_SUBJECTS": (),
         "OPERATIONAL_PHRASES": ()},
    ),
]


def restore() -> None:
    for name, value in PRISTINE.items():
        setattr(classifier, name, copy.deepcopy(value))


def verdicts(emails) -> dict:
    """What the classifier currently answers for every email."""
    return {
        e.email_id: classifier.classify(
            e.subject, e.body, e.domain, e.attachments).category
        for e in emails
    }


def residue(emails) -> int:
    """What the old rubric criterion counted: rules that will not decide."""
    return sum(
        1 for e in emails
        if classifier.classify(
            e.subject, e.body, e.domain, e.attachments).confidence < FLOOR
    )


def measure(emails) -> dict:
    res = evaluate()
    strict = res["strict"]
    return {
        "verdicts": verdicts(emails),
        "macro_f1": strict.macro_f1,
        "accuracy": strict.accuracy,
        "wrong": len(strict.wrong),
        "split_templates": len(res["split"]),
        "inconsistent": res["inconsistent_emails"],
        "residue": residue(emails),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    emails = BundleMailSource(ROOT / "data").emails()

    restore()
    base = measure(emails)
    if base["macro_f1"] < 1.0 or base["split_templates"]:
        print("the classifier does not pass its own checks before mutation:")
        print(f"  macro-F1 {base['macro_f1']:.4f}, "
              f"{base['split_templates']} split template(s)")
        print("fix that first - a mutation score means nothing from here.")
        return 2

    rows = []
    for m in MUTANTS:
        restore()
        m.apply()
        try:
            got = measure(emails)
        finally:
            restore()

        # An "equivalent mutant": the rules changed, the answers did not. It
        # is not a hole in the harness - there is nothing to catch. Counting
        # one as a survivor would understate the harness; counting it as a
        # kill would flatter it. Both are reported, separately.
        moved = sum(1 for k, v in got["verdicts"].items()
                    if base["verdicts"].get(k) != v)

        by_accuracy = got["macro_f1"] < base["macro_f1"]
        by_consistency = got["split_templates"] > base["split_templates"]
        # What the harness used to rely on. A mutant only "caught" here if the
        # residue rose: the rubric's check was one-sided, so a mutation that
        # made the rules decide *more* passed it.
        by_residue = got["residue"] > base["residue"]

        rows.append({
            "name": m.name, "what": m.what,
            "moved": moved,
            "equivalent": moved == 0,
            "killed": by_accuracy or by_consistency,
            "by_accuracy": by_accuracy,
            "by_consistency": by_consistency,
            "by_old_residue_check": by_residue,
            **got,
        })

    equivalent = [r for r in rows if r["equivalent"]]
    live = [r for r in rows if not r["equivalent"]]
    killed = [r for r in live if r["killed"]]
    survived = [r for r in live if not r["killed"]]
    old = [r for r in live if r["by_old_residue_check"]]

    if args.json:
        print(json.dumps({
            "mutants": len(rows),
            "changed_an_answer": len(live),
            "equivalent": len(equivalent),
            "killed": len(killed),
            "survived": len(survived),
            "killed_by_old_residue_check": len(old),
            "baseline": {k: v for k, v in base.items() if k != "verdicts"},
            "detail": [{k: v for k, v in r.items() if k != "verdicts"}
                       for r in rows],
        }, indent=2))
        return 0 if not survived else 1

    print("=" * 74)
    print("CLASSIFIER MUTATION  (does the harness notice a broken classifier?)")
    print("=" * 74)
    print(f"  baseline: macro-F1 {base['macro_f1']:.4f}, "
          f"{base['split_templates']} split templates, "
          f"residue {base['residue']}/{len(emails)}")
    print()
    for r in rows:
        mark = ("no effect" if r["equivalent"]
                else "killed   " if r["killed"] else "SURVIVED ")
        how = ",".join(
            x for x in (
                "accuracy" if r["by_accuracy"] else "",
                "consistency" if r["by_consistency"] else "",
            ) if x
        ) or "-"
        tail = "no answer changed" if r["equivalent"] else f"by {how}"
        print(f"  [{mark}] {r['name']:<32} {tail}")
        if args.verbose:
            print(f"               {r['what']}")
            print(f"               {r['moved']} answers moved  "
                  f"macro-F1 {r['macro_f1']:.4f}  {r['wrong']} wrong  "
                  f"{r['split_templates']} split ({r['inconsistent']} emails)  "
                  f"residue {r['residue']}")
    print("-" * 74)
    print(f"  mutants                : {len(rows)}")
    print(f"  changed an answer      : {len(live)}  "
          f"({len(equivalent)} changed none, so there was nothing to catch)")
    print(f"  killed                 : {len(killed)}/{len(live)}")
    print(f"  the old residue check  : {len(old)}/{len(live)}")
    print()
    print("  The residue figure is one-sided - it only ever rose when rules")
    print("  decided less - so a mutation that made the rules decide more, and")
    print("  wrongly, passed it. That is how a classifier filing berthing")
    print("  reports as invoice questions scored better than the real one.")
    print()

    if equivalent:
        print(f"  The {len(equivalent)} that changed nothing are worth reading")
        print("  rather than dismissing. Each is a rule that cannot matter on")
        print("  this corpus, either because something earlier already decided")
        print("  or because a second rule catches the same mail. Spam is the")
        print("  second kind: deleting the sender list changes no verdict, and")
        print("  neither does deleting every spam phrase - but deleting both")
        print("  loses forty emails, which is why that is a mutant of its own.")
        print()

    print(f"SUMMARY mutants={len(rows)} live={len(live)} "
          f"killed={len(killed)} equivalent={len(equivalent)} "
          f"old_check_killed={len(old)}")
    print()

    if survived:
        print("  A surviving mutant is a hole in the harness, not a quirk of")
        print("  the mutant: something can be made wrong here without any")
        print("  check going red. Add the case that would catch it.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
