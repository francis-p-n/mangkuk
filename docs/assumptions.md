# Assumptions, resolved and open

The brief itself, and where each requirement is met, is in
[requirements.md](requirements.md). This file covers what it leaves open.

No ground truth ships with the bundle, so some decisions are judgement calls.
Each one below is isolated behind a flag or a constant, so it can be flipped in
one line once the organizers' scorer gives feedback.

## 1. Emails chasing a draft BL — resolved

91 emails (17.5% of the inbox) carry no attachment and say, in one identical
sentence:

> Please assist to send the draft BL for SIN832764835 for checking asap.

Two readings were possible: an operational chaser (**GENERAL**), or a
comparison request that cannot proceed (**BL_COMPARISON** +
`missing_attachment`). This matters more than any other single call in the
corpus, because Stage 1 is scored by macro-F1 — misfiling 91 emails damages
two categories at once.

**Resolved: GENERAL.** Four pieces of corpus evidence, all pointing the same
way. The investigation confirmed the existing default rather than changing it,
so no output moved.

**1 — The organizers hand-built zero-attachment `missing_attachment` cases,
and worded them differently.** Emails 506, 508 and 510 carry no attachment at
all — structurally identical to a chaser — and read:

> Please compare the SI and draft BL for 070500263211 and confirm (attachments
> appear to have been dropped).

All 3 say *compare*; 0 of the 91 chasers do. All 91 chasers say *send the
draft*; 0 of the constructed cases do. The separation is total. If having no
attachment were by itself enough to make an email a failed comparison,
building those three would have been pointless.

**2 — Counting them as comparisons breaks the 5/5/5/5 block.** Emails 501–520
are plainly constructed as five cases of each escalation reason. Folding the
chasers in makes `missing_attachment` 96 against 5, 5 and 5 for the others.

**3 — The corpus already has a convention for attachment-less workflow mail.**
All 132 `SI_REQUEST` emails carry zero attachments and say *"Please find
Shipping instruction for 5RUS-…"* — a document named, none attached, and
nobody would call those `missing_attachment`. Attachment-less workflow mail
gets a workflow category, not an escalation. The chasers are the BL-side
analogue; with no `BL_REQUEST` category on offer, they land in GENERAL.

**4 — The reference number inside a chaser is filler.** 33 chasers carry a
booking reference in the subject *and* another in the body. They never match —
0 of 33. No chaser's body reference appears anywhere else in the corpus:
not in another email (0 of 91), not in any attachment (0 of 91). And no OC
number from a chaser appears in any of the 129 real document checks — zero
overlap between 78 chaser OC numbers and 116 comparison OC numbers. The
chaser body is a template with a random token dropped into it. There is no
shipment behind it to compare against.

**The flag stays.** `python run.py --chase-as-comparison` still flips them,
moving BL_COMPARISON from 129 to 220 and `missing_attachment` from 5 to 96. It
costs one line to keep and it is the cheapest available insurance if the
organizers' scorer disagrees. The evidence above is why it is off by default.

Pinned as tests: `tests/test_chasers.py` — 14 assertions over the corpus, so
the argument fails loudly if it ever stops being true.

## 2. Party comparison uses the name, not the address

Text documents put the address on a continuation line; spreadsheets pack it
into the same cell after a `|`. Both are captured as `detail` and shown as
evidence, but only the company name is compared. Addresses carry far more
formatting noise than signal, and every party defect in the corpus is a
different company, not a different address for the same one.

## 3. A confirmed defect outranks an unreadable field

If one field genuinely conflicts and another cannot be read, the verdict is
`MISMATCH`, not `NEEDS_REVIEW`. The defect is real and actionable; escalating
the whole email would bury a caught defect. Scoring rewards defects caught
end-to-end, and an ops person would rather see "consignee is wrong, and we
could not read the weight" than a bare "needs review".

## 4. A missing part of a port is not a conflict

`SINGAPORE` vs `SINGAPORE (SGSIN)` agrees — one side simply carries less
information. `MOMBASA, KENYA (KEMBA)` vs `TUTICORIN, INDIA (KEMBA)` conflicts,
because both sides state a city and they disagree. Only present-and-different
counts.

## 5. PDFs are declared unreadable rather than guessed

28 PDF attachments (15 comparison emails) resolve to
`NEEDS_REVIEW / unreadable`. Adding OCR is Tier 4 work; a declared-unreadable
document is a correct answer, and a hallucinated one is not.
