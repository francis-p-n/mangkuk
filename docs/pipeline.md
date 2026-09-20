# How the pipeline works

## The problem

A shipping documentation desk receives one inbox containing document checks,
requests for new shipping instructions, invoice questions, operational updates
and spam. For a document check, someone opens two attachments and compares
seven fields by eye. It is repetitive, it is easy to miss one, and the two
documents deliberately disagree on vocabulary — `Port of Loading` on one,
`Load Port` on the other. A missed discrepancy becomes a corrected BL, a delay
and rework.

## How it works

Four stages. The fuzzy work and the decisive work are deliberately separated.

**1. Triage** — five categories, rules first. The intent in this corpus lives
in a small set of body templates, so paying a model to read them would be
daft. The security banner and quoted reply chains are stripped before matching.

**2. Extraction** — pull the seven fields out of each document. 66 distinct
labels appear across the corpus for these seven concepts, including
`Gross Weight毛重(KGS)` and the compound `Notify Party/Intermediate Consignee`.
Alignment is by meaning, never by header text. Every value keeps its source
line, label and line number.

**3. Comparison** — ordinary deterministic code, no model. Company suffixes,
thousands separators, container specs and port tuples each normalize their own
way. This is the part that must be reproducible, unit-testable and
explainable, so it is not left to a language model. The model's job upstream is
to *locate* values; this stage decides whether two located values mean the same
thing.

**4. Agent recovery** — an LLM gets one attempt at whatever the deterministic
parsers left missing, before anyone is asked to look. It is never believed on
its word; see [validation](validation.md).

**5. Escalation** — when the system still cannot decide, it says so and why,
rather than guessing: `wrong_doc_type`, `missing_attachment`, `unreadable`,
`missing_value`.

### The cascade, and where the model sits in it

```
labelled parse  ->  block parse  ->  resolver agent  ->  escalate
  deterministic     deterministic     grounded LLM       a person
```

Cheapest and most certain first. The model is reached only for fields two
deterministic parsers could not find, which on this corpus is 3 fields across
2 documents — so the agent is insurance against unseen layouts rather than the
main engine, and it costs almost nothing to run.

**The model can find a value. It cannot author one.** Every proposal must come
back with a verbatim quote; the quote must actually appear in the document;
the value must appear inside the quote; and typed fields must still parse as
their type. A proposal failing any check is discarded and the field stays
missing, so the email escalates exactly as if the agent had never run. Whatever
survives goes through the same deterministic comparator as every other field.

This is what makes an LLM safe here. A model that invents `TOTALLY MADE UP
TRADING LLC` produces a plausible-looking consignee, and a plausible-looking
consignee on a bill of lading is worse than no answer at all.

The same agent decides the classifications the rules abstain on — 59 of 520
emails, judged one at a time. The 91 draft-chasers are no longer among them:
[docs/assumptions.md](assumptions.md) settles that question on corpus
evidence, so a rule decides them and no tokens are spent.

Run it with `--agent bedrock` (Claude on Amazon Bedrock, so document text
stays inside the tenant), `--agent anthropic`, or `--agent gemini`
(`GEMINI_API_KEY`, model via `SDOC_GEMINI_MODEL`). The default is `off`, which
keeps the scored run fully deterministic and reproducible.

The provider is one method behind a protocol, so swapping it is a small class
and nothing downstream changes. It matters less than it looks: the grounding
checks mean a weaker or cheaper model cannot do damage, only abstain. Bedrock
is the one to present, because it keeps document text inside the tenant.

Two outputs. `out/submission.json` is the narrow shape the scorer wants.
`out/results.json` carries everything a human needs — evidence lines, shipment
references, per-field comparisons — and is what the workspace UI reads.

### Design decisions worth defending

**Glass box, not black box.** Every flagged field ships with both raw values,
both source labels and both line numbers. An ops person cannot email a carrier
saying "the AI says your consignee is wrong" — they need the two lines, side by
side, quotable.

**The filename is not evidence.** Five attachments in the bundle are named
`_SI` or `_BL` but contain a packing list, a certificate of origin or a
commercial invoice. Every document's type is read from its own title block
before extraction. Trusting the filename means confidently extracting seven
shipment fields out of a packing list.

**One mail interface.** The pipeline only ever talks to `MailSource`. The
bundle is one implementation; a Microsoft Graph mailbox would be another, and
nothing downstream would change.

### Ranking the work

The comparator says *whether* seven fields agree and nothing about which
disagreement matters. `sdoc/severity.py` supplies that: one table, rank and
reason side by side, so an operations team can argue with the judgement in
one edit rather than argue with a score.

| Rank | Field | Because |
|---:|---|---|
| 1 | consignee | names who may take delivery |
| 2 | shipper | title at origin, and who may amend the bill |
| 3 | port_of_discharge | cargo discharged in the wrong country |
| 4 | gross_weight_kg | the declaration a terminal verifies against |
| 5 | port_of_loading | routing, rating, and the carrier's records |
| 6 | notify_party | nobody is told the cargo arrived; storage accrues |
| 7 | container_count | an amended bill and a corrected invoice |

A draft is as bad as its single worst field — the fields are not summed,
because three routine errors do not add up to a wrong consignee. The count
only breaks ties within a rank. Three bands, because a person triaging a
queue can hold three in mind and not seven; the bundle splits 13 / 23 / 10,
so the ordering is doing real work.

### Learning from the desk

A clerk disagreeing with a verdict is the most informative event this system
sees, and normally it is said out loud and lost. `sdoc/learned.py` records it
as an override: one field, one pair of values, and what the person said is
true.

Three restrictions, because "the user can teach it" is also the shape of a
checker being quietly switched off:

1. **One exact pair, never a pattern.** Teaching it about two spellings of
   Roxcel says nothing about any other pair, so an override cannot widen on
   its own. An override where both sides read the same value is refused
   outright: there is no pair there, and it would apply everywhere.
2. **Off unless asked for.** `run.py` applies nothing without `--learned`,
   so the scored submission stays reproducible from the repo alone.
3. **Never quiet.** `tools/apply_overrides.py` reports every verdict in the
   inbox that would move, marking the ones that stop a difference being
   reported, before anything is written. Every override carries who recorded
   it and when.

An override settles a disagreement; it is not a source of values. A field the
parsers never found stays undecidable, whatever the file says.

`--write` then generates `eval/learned_cases.py`, which runs with the test
suite. That is the part worth the effort: a clerk's judgement stops being a
note on one email and becomes an assertion that keeps being checked. The
report also separates corrections the base rules could already handle — those
are a missing rule in `normalize/` and should be fixed there — from the ones
that are irreducible facts about two companies.

## What it does today

520 emails, end to end, in about a second.

| Category | Count |
|---|---:|
| GENERAL | 150 |
| SI_REQUEST | 141 |
| BL_COMPARISON | 129 |
| INVOICE_QUERY | 60 |
| SPAM | 40 |

Of the 129 document checks:

| Outcome | Count | Share |
|---|---:|---:|
| OK — all seven fields agree | 63 | 48.8% |
| MISMATCH — at least one defect | 46 | 35.7% |
| NEEDS_REVIEW — escalated | 20 | 15.5% |

**109 of 129 decided without a human (84.5%).** Of those decided, 42.2%
carried at least one defect.

Escalations, by reason: exactly **five each** of `wrong_doc_type`,
`missing_attachment`, `unreadable` and `missing_value`.

That symmetry is not a coincidence and is the strongest accuracy signal
available without ground truth. Emails 501-520 are a constructed edge-case
block — five per reason — and the pipeline now resolves all twenty the way
they were built. Two of them were being reported as defects until this was
spotted; see *Unfilled forms are not values* in [validation](validation.md).

Defects found, by field: container count 19, port of discharge 13, gross
weight 12, notify party 8, consignee 7, shipper 7, port of loading 6.
