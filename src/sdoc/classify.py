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
)
# Chasing a draft that has not arrived yet. Nothing to compare, so this is not
# a comparison task — see docs/assumptions.md.
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

    `chase_as_comparison` decides the single biggest open question in this
    corpus: 91 emails ask a counterparty to *send* a draft BL for checking and
    carry no attachment. Either they are operational chasers (GENERAL), or they
    are comparison requests that cannot proceed (BL_COMPARISON +
    missing_attachment). See docs/assumptions.md — flip the flag to switch.
    """
    subj = subject.lower()
    text = clean_body(body).lower()

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
            return Classification("BL_COMPARISON", "chasing_draft_bl", 0.60)
        return Classification("GENERAL", "chasing_draft_bl", 0.60)

    if any(p in text for p in SI_PHRASES) or any(s in subj for s in SI_SUBJECTS):
        return Classification("SI_REQUEST", "si_workflow", 0.92)

    if any(p in text for p in INVOICE_PHRASES) or any(s in subj for s in INVOICE_SUBJECTS):
        return Classification("INVOICE_QUERY", "invoice_signal", 0.90)

    return Classification("GENERAL", "default", 0.55)
