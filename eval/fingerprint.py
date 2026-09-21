#!/usr/bin/env python3
"""What template is this email written from?

    python eval/fingerprint.py            # the clusters, largest first
    python eval/fingerprint.py --show 7   # every email in cluster 7

WHY THIS EXISTS

No ground truth ships with the bundle, so until now nothing measured whether
the classifier was *right* - only how much of the corpus its rules were
willing to decide. Those are different numbers, and the difference is not
academic: broadening one invoice rule until 55 berthing reports and a time-off
request were filed as invoice questions left every test green and *improved*
the published residue figure from 59 to 4. A harness that scores a worse
classifier better is worse than no harness.

The honest fix is labels. Labelling 520 emails by hand is a day's work nobody
has, and labelling them with the classifier's own phrase lists would only ask
the classifier whether it agrees with itself.

This is the third way. The corpus is generated from a small set of templates,
and a template is visible in the shape of a message once the particulars are
taken out of it. Strip the security banner, the greeting, the quoted reply and
the signature block; keep the opening clause; replace every name, port,
vessel, reference and number with a placeholder. What is left is the sentence
the template was built from, and emails written from one template collapse
onto one string.

33 of those cover all 520 emails. A person reads 33 exemplars and decides 33
times; `eval/gold/clusters.json` records those decisions with the exemplar
each one was made from. That is a real ground truth, made by a human, at a
cost a human can pay.

INDEPENDENCE

Nothing here imports `sdoc.classify` or reuses a word from its phrase lists.
The banner and quoted-reply patterns are re-derived rather than shared: if the
two implementations ever disagree about where a message ends, that is a fact
worth finding out, not a duplication to tidy away.

The abbreviation list below is the one place domain vocabulary enters, and it
is a list of shipping abbreviations, not of intents: keeping `SI` and `BL` as
themselves is what stops "send the draft BL" and "send the draft invoice"
collapsing onto the same template.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdoc.mailsource import BundleMailSource        # noqa: E402

BANNER = re.compile(r"^\s*WARNING:.*?$", re.I | re.M)
QUOTED = re.compile(r"^_{5,}\s*$", re.M)
SIGNOFF = re.compile(
    r"^\s*(best regards|best|regards|thanks|thank you|kind regards|cheers"
    r"|sincerely|yours (faithfully|sincerely))\b[,.]?\s*$",
    re.I,
)
GREETING = re.compile(r"^\s*(hi|hello|dear)\b", re.I)
TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d[\d,.\-/]*|&")

# Shipping abbreviations that carry meaning rather than identity. Everything
# else in capitals is a name, a port, a vessel or a code, and becomes `~`.
ABBREVIATIONS = {
    "si", "bl", "po", "oc", "gr", "thc", "dd", "eta", "etd", "rpa", "hss",
    "sd", "mt", "kg", "fcl", "lcl", "awb", "hbl", "mbl", "vgm", "pol", "pod",
    "cy", "fob", "cif", "ex",
}

# The opening clause carries the intent; what follows is detail. Cutting here
# is what collapses 118 shipping instructions that differ only in how many
# fields the customer filled in.
CLAUSE = 18


def intent(body: str) -> str:
    """The part of the message that says what is being asked."""
    text = QUOTED.split(BANNER.sub("", body))[0]
    kept: list[str] = []
    for line in text.splitlines():
        if SIGNOFF.match(line):
            break
        if GREETING.match(line):
            continue
        kept.append(line)
    return " ".join(" ".join(kept).split())


def skeleton(text: str, cap: int = CLAUSE) -> str:
    """The template, with every particular replaced by `~`."""
    out: list[str] = []
    for token in TOKEN.findall(text):
        low = token.lower()
        keep = token.islower() or low in ABBREVIATIONS
        piece = low if keep else "~"
        if piece == "~" and out and out[-1] == "~":
            continue                       # a run of particulars is one gap
        out.append(piece)
    return " ".join(out[:cap])


def fingerprint(subject: str, body: str) -> str:
    """The template this email was written from.

    Falls back to the subject when the body says nothing - eleven messages in
    this corpus are a greeting and a signature, with the whole content in the
    subject line.
    """
    shape = skeleton(intent(body))
    if shape.strip("~ "):
        return shape
    return "SUBJECT:" + skeleton(subject, 12)


@dataclass
class Cluster:
    fingerprint: str
    emails: list           # list[Email]

    @property
    def size(self) -> int:
        return len(self.emails)

    @property
    def exemplar(self):
        return self.emails[0]

    @property
    def id(self) -> str:
        """A short stable name, so a label can refer to a cluster in writing."""
        return hashlib.sha1(self.fingerprint.encode("utf-8")).hexdigest()[:10]

    def signals(self) -> dict:
        """Evidence about this cluster that does not come from its wording.

        A cluster whose members disagree about these is not one template, and
        a single label for it would be wrong for some of its emails. The
        scorer refuses to use an impure cluster as ground truth.
        """
        docs = {has_shipping_docs(e) for e in self.emails}
        senders = {e.domain for e in self.emails}
        return {
            "attachments_agree": len(docs) == 1,
            "carries_documents": docs == {True},
            "sender_domains": len(senders),
        }

    @property
    def pure(self) -> bool:
        return bool(self.signals()["attachments_agree"])


def has_shipping_docs(email) -> bool:
    return any("_SI." in a or "_BL." in a for a in email.attachments)


def clusters_of(emails) -> list[Cluster]:
    grouped: dict[str, list] = collections.defaultdict(list)
    for e in emails:
        grouped[fingerprint(e.subject, e.body)].append(e)
    out = [Cluster(f, sorted(es, key=lambda e: e.email_id))
           for f, es in grouped.items()]
    return sorted(out, key=lambda c: (-c.size, c.fingerprint))


def load(source: str | Path = None) -> list[Cluster]:
    src = BundleMailSource(Path(source) if source else ROOT / "data")
    return clusters_of(src.emails())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", type=int, metavar="N",
                    help="print every email in cluster N")
    ap.add_argument("--exemplars", action="store_true",
                    help="print the opening clause of each cluster's exemplar")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    args = ap.parse_args()

    cs = load()
    total = sum(c.size for c in cs)

    if args.json:
        print(json.dumps([{
            "id": c.id, "size": c.size, "fingerprint": c.fingerprint,
            "exemplar": c.exemplar.email_id, "pure": c.pure,
            "emails": [e.email_id for e in c.emails],
        } for c in cs], indent=2))
        return 0

    if args.show is not None:
        c = cs[args.show]
        print(f"cluster {args.show}  ({c.size} emails, id {c.id})")
        print(f"  {c.fingerprint}\n")
        for e in c.emails:
            print(f"  {e.email_id}  {e.subject[:70]}")
        print("\nexemplar in full:\n")
        print(c.exemplar.body[:1200])
        return 0

    print(f"{total} emails, {len(cs)} templates, "
          f"{sum(1 for c in cs if c.size == 1)} of them singletons")
    print(f"{sum(1 for c in cs if not c.pure)} template(s) mix attachment "
          f"shapes and cannot be labelled as one thing\n")
    cum = 0
    for i, c in enumerate(cs):
        cum += c.size
        mark = " " if c.pure else "!"
        print(f"{i:3}{mark} {c.size:4} {100 * cum // total:3}%  {c.id}  "
              f"{c.fingerprint[:88]}")
        if args.exemplars:
            print(f"                        {c.exemplar.email_id}: "
                  f"{intent(c.exemplar.body)[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
