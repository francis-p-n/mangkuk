# Assumptions and open questions

No ground truth ships with the bundle, so some decisions are judgement calls.
Each one below is isolated behind a flag or a constant, so it can be flipped in
one line once the organizers' scorer gives feedback.

## 1. Emails chasing a draft BL — the big one

91 emails (17.5% of the inbox) say some variant of:

> Please assist to send the draft BL for SIN832764835 for checking asap.

They carry no attachment. Two readings:

- **GENERAL** (current default) — an operational chaser. Nothing has arrived,
  so there is nothing to compare.
- **BL_COMPARISON + `missing_attachment`** — a comparison request that cannot
  proceed.

**Why the default is GENERAL:** exactly two emails in the corpus carry one
attachment instead of two (`email_507`, `email_509`, both SI-only). That looks
like a deliberately constructed `missing_attachment` case. If the 91 chasers
were also meant to be `missing_attachment`, building those two would have been
pointless.

**How to flip it:** `python run.py --chase-as-comparison`. This moves
BL_COMPARISON from 126 to 217 and `missing_attachment` from 2 to 93. Generate
both, and ask the organizers which scores better — it is the single highest-value
question to put to them.

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
