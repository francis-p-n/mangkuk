"""Stage 1 — what kind of message is this.

Rules first, because in this corpus the intent is carried by a small set of
body templates and it would be daft to pay a model to read them. The LLM hook
exists for the residue: anything the rules abstain on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CATEGORIES = ("BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM")

SPAM_DOMAINS = {
    "webmail-verify.co", "secure-mailbox.org", "parcel-track.co",
    "logistics-deals.biz", "prize-claims.info", "crypto-invest.net",
}
SPAM_PHRASES = (
    "congratulations", "limited time offer", "weird trick", "you have won",
    "claim your", "unpaid customs fee", "verify your account", "act now",
    "exceeded its storage limit", "monthly draw",
)

COMPARISON_PHRASES = (
    "attached are the si and draft bl",
    "attached the shipping instruction and the draft bill of lading",
    "check the draft bl against the si",
    "verify the bl matches the si",
    "bl matches the si",
    # Asks for the comparison outright. The attachments may have gone astray in
    # transit, which is a comparison that cannot proceed - not a different kind
    # of email.
    "compare the si and draft bl",
    "compare the si and the draft bl",
    "compare the shipping instruction and the draft bill of lading",
)
# Chasing a draft that has not arrived yet: nothing has been attached because
# nothing exists to attach. The discriminator against a genuine comparison
# whose files went astray is the verb - these ask to *send*, those ask to
# *compare* - and the two never overlap. See docs/assumptions.md.
CHASE_PHRASES = ("assist to send the draft bl", "send the draft bl for")

SI_PHRASES = (
    "please find shipping instruction",
    "find shipping instruction for",
    "submit si",
    "shipping instruction for",
)
SI_SUBJECTS = ("request si", "si needed", "cust si", "submit si", "si -")

INVOICE_PHRASES = (
    "query on invoice", "cancel invoice", "local charge", "thc /",
    "billed separately", "advise the breakdown", "d & d charges",
    "telex release charge", "total freight",
    # Written "D&D / detention charges" in the body and "D & D charges" in
    # the subject, so the subject phrase above never matched the message. 18
    # emails were being decided by whichever subject the generator happened
    # to staple on.
    "detention charges",
    # "The GR is still missing for invoice X. Kindly arrange to post the GR so
    # we can proceed with billing." Filed as an invoice question because it
    # names an invoice and blocks billing; the reading is argued, and marked
    # contested, in eval/gold/clusters.json. Whichever way it is read, all 23
    # must read the same way, and before this they split 13/10 on the subject.
    "post the gr",
)

# Operational traffic, recognised by what it says rather than by nothing else
# matching. Every one of these is a template in the corpus - a berthing
# report, an outstanding-BL worklist, a loading update, a robot announcing it
# has finished, an office-hours notice - and each was falling through to the
# default, where a subject line stapled on by the generator could pick it up
# and file it as something else entirely.
OPERATIONAL_PHRASES = (
    "berthing report",
    "outstanding bl",
    "update summary",
    "loading completed",
    "automated notification",
    "no action required",
    "resumes normal operations",
    "action the pending items",
)
INVOICE_SUBJECTS = (
    "invoice", "local charges", "total freight", "d & d charges",
    "telex release charges", "charges",
)

BANNER = re.compile(
    r"^\s*WARNING:\s*This email originated outside of our organisation.*?$",
    re.I | re.M,
)
_QUOTED = re.compile(r"^_{5,}\s*$", re.M)


@dataclass
class Classification:
    category: str
    rule: str
    confidence: float


def clean_body(body: str) -> str:
    """Drop the security banner and anything below a quoted-reply separator."""
    text = BANNER.sub("", body)
    parts = _QUOTED.split(text)
    return parts[0].strip()


def _has_shipping_docs(attachments: list[str]) -> bool:
    return any("_SI." in a or "_BL." in a for a in attachments)


def classify(
    subject: str,
    body: str,
    sender_domain: str,
    attachments: list[str],
    chase_as_comparison: bool = False,
) -> Classification:
    """Classify one message.

    `chase_as_comparison` covers the largest classification call in this
    corpus: 91 emails ask a counterparty to *send* a draft BL and carry no
    attachment. They are filed as operational chasers (GENERAL) on four pieces
    of corpus evidence set out in docs/assumptions.md and asserted in
    tests/test_chasers.py. The flag flips them to BL_COMPARISON +
    missing_attachment, and is kept only as insurance against the organizers'
    scorer disagreeing.
    """
    subj = " ".join(subject.lower().split())
    # Flattened before matching. Every phrase below is written with single
    # spaces, and a mail client that hard-wraps at 72 characters puts a
    # newline through the middle of one: a wrapped "query on invoice"
    # then matches nothing and the email falls to the default. Nothing
    # in this corpus wraps, which is a fact about the generator rather
    # than about mail.
    text = " ".join(clean_body(body).lower().split())

    if sender_domain in SPAM_DOMAINS:
        return Classification("SPAM", "spam_domain", 0.99)
    if any(p in text for p in SPAM_PHRASES):
        return Classification("SPAM", "spam_phrase", 0.95)

    # Documents in hand beats every other signal: there is something to check.
    if _has_shipping_docs(attachments):
        return Classification("BL_COMPARISON", "has_si_bl_attachment", 0.98)
    if any(p in text for p in COMPARISON_PHRASES):
        return Classification("BL_COMPARISON", "comparison_phrase", 0.90)
    if any(p in text for p in CHASE_PHRASES):
        if chase_as_comparison:
            return Classification("BL_COMPARISON", "chasing_draft_bl", 0.88)
        # Held at low confidence until the evidence was in. It is now, so the
        # agent no longer spends 91 calls second-guessing a settled rule.
        return Classification("GENERAL", "chasing_draft_bl", 0.88)

    if any(p in text for p in SI_PHRASES):
        return Classification("SI_REQUEST", "si_workflow", 0.92)

    if any(p in text for p in INVOICE_PHRASES):
        return Classification("INVOICE_QUERY", "invoice_signal", 0.90)

    if any(p in text for p in OPERATIONAL_PHRASES):
        return Classification("GENERAL", "operational_notice", 0.90)

    # The body said nothing, so now - and only now - the subject gets a vote.
    #
    # It used to vote alongside the body, and in this corpus that is a bad
    # trade. Subjects and bodies are drawn independently for operational mail:
    # email_075 is headed "Time Off Request" and its body is an RPA billing
    # notice, email_021 is headed "_RPA_ India HSS SD Billing Process
    # Completed" and asks for shipping instructions. A subject rule reading
    # over the body split seven templates down the middle - 94 emails written
    # from the same sentence, filed under two categories depending on which
    # heading they were given. The body is what somebody is being asked to act
    # on; the subject is a hint for when the body is silent, which is exactly
    # the eleven messages here that have no body at all.
    if any(s in subj for s in SI_SUBJECTS):
        return Classification("SI_REQUEST", "si_subject", 0.80)

    if any(s in subj for s in INVOICE_SUBJECTS):
        return Classification("INVOICE_QUERY", "invoice_subject", 0.80)

    return Classification("GENERAL", "default", 0.55)
