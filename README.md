# SDOC — shipping document verification

Reads a shipping operations inbox, works out what each message is, and for
every draft Bill of Lading checks it against the Shipping Instruction that
authorised it — field by field, with the source lines attached so a person can
check the machine rather than trust it.

Built for the Averis hackathon against the supplied 520-email bundle.

```bash
python run.py
```

```bash
python -m pytest tests -q
```

```bash
python eval/mutation.py
```

```bash
python eval/audit.py
```

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

**4. Escalation** — when the system cannot decide, it says so and why, rather
than guessing: `wrong_doc_type`, `missing_attachment`, `unreadable`,
`missing_value`.

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

## What it does today

520 emails, end to end, in about a second.

| Category | Count |
|---|---:|
| GENERAL | 153 |
| SI_REQUEST | 141 |
| BL_COMPARISON | 126 |
| INVOICE_QUERY | 60 |
| SPAM | 40 |

Of the 126 document checks:

| Outcome | Count | Share |
|---|---:|---:|
| OK — all seven fields agree | 57 | 45.2% |
| MISMATCH — at least one defect | 44 | 34.9% |
| NEEDS_REVIEW — escalated | 25 | 19.8% |

**101 of 126 decided without a human (80.2%).** Of those decided, 43.6%
carried at least one defect.

Escalations, by reason: `unreadable` 15 (PDF attachments, not yet supported),
`wrong_doc_type` 5 (the decoys), `missing_value` 3 (blank or `N/A` in the
source), `missing_attachment` 2.

Defects found, by field: container count 17, port of discharge 14, gross
weight 9, notify party 8, consignee 7, port of loading 7, shipper 7.

## Testing and validation

There is no ground truth in the bundle, so accuracy is established three ways.

### 1. Test suite — 124 tests, all passing

```
124 passed in 0.95s
```

Unit tests cover every normalization rule, every label alias including the
traps, document identification across `.txt`/`.xlsx`/`.docx`/`.pdf`, all four
escalation reasons and the precedence between them, the classifier, and
submission validation. Two traps are pinned explicitly because a naive
implementation gets them wrong:

- `Notify Party/Intermediate Consignee` contains both words and must resolve to
  notify party, not consignee.
- `NET WEIGHT` and `Kinds of Packages; Description of Goods` must not be
  captured as gross weight or container count.

The integration test runs the real bundle and pins 18 hand-verified cases —
seven known defects with their exact field lists, three known-clean drafts, and
eight known escalations. These are the guard against a normalization tweak
quietly breaking a defect already being caught.

### 2. Defect injection — 555 injected, 100% caught

`eval/mutation.py` takes every pair the pipeline calls clean, injects one known
defect into the draft BL, and checks that exactly that field is reported.

```
clean pairs available as mutation hosts: 57
injected defects : 555
caught           : 555  (100.0%)
caught cleanly   : 555  (100.0% - no collateral fields)
control failures : 0
```

Ten injection strategies across the seven fields, including the two subtle
ones: a port where only the UN/LOCODE is wrong while the city still reads
correctly, and a container spec where the count is right but the box type
changed. Every one was caught, none produced a collateral false flag on another
field, and the unmutated control run stayed silent.

### 3. No-ground-truth audit

`eval/audit.py` asks where the system could be wrong.

**Normalization sensitivity.** Of 654 field agreements, 642 (98.2%) are
byte-identical strings. Normalization decided only 12 — five thousands
separators (`243588` vs `243,588`) and seven ports where one side omits the
UN/LOCODE. Every one was inspected by hand. The comparator is doing very
little quiet work, which is the point.

**Classifier residue.** 62 of 520 emails (11.9%) fall through every rule to the
default. These are the genuine judgement calls — RPA billing notifications,
berthing reports, a time-off request — and they are precisely the residue an
LLM stage should own. Rules handle 88.1% at high confidence.

**Unmapped labels.** Every label in the corpus that maps to no field was
reviewed. All are legitimately outside the seven — freight terms, HS codes,
vessel and voyage, booking references.

### Known limits

PDFs are not read, so 15 comparison emails escalate as `unreadable`. That is a
deliberate choice: a declared-unreadable document is a correct answer and a
hallucinated one is not. The largest open question is documented in
[docs/assumptions.md](docs/assumptions.md) — 91 emails chasing a draft BL are
currently GENERAL, and `--chase-as-comparison` flips them.

## Business viability

**What it replaces.** A clerk opening two attachments and eye-comparing seven
fields. Assuming five minutes per check — an estimate to confirm with the
operations team, not a measured figure — the 126 checks in this batch are about
**10.5 hours** of desk time.

The system decides 101 of them outright and escalates 25 with the reason
already stated. At roughly two minutes to action a pre-diagnosed escalation,
that is about **50 minutes of human time**, against 10.5 hours. The saving is
in the same order as the work itself, and it scales with volume rather than
headcount.

**Where the money actually is.** Not the minutes — the 44 defective drafts
caught before release. A wrong consignee or port on a released BL means an
amendment fee, a delayed release, and in the worst case cargo moving against a
document naming the wrong party. Catching those is worth more than the clerical
time, and the system caught them at a rate of 43.6% of decided checks.

**Why an ops team would actually use it.** The unit on screen is a shipment,
not an email. The vocabulary is "needs correction", not `MISMATCH`. Every flag
shows both values and the labels they came from, so the correction email
writes itself and the clerk stays accountable for sending it. Nothing is
auto-sent.

**Adoption risk, handled.** The system never guesses. 19.8% of checks come back
as "a person needs to look at this, and here is exactly why". A tool that
silently guessed on those would be abandoned the first time it was wrong on
something expensive.

**Deployment shape.** Graph API webhook into API Gateway and Lambda, S3 for
attachments, SQS between stages so one corrupt document fails one message
rather than a batch, Bedrock for the model calls so data stays inside the
tenant, DynamoDB keyed on OC number, static front end on S3 and CloudFront.
The stage boundaries are already JSON contracts, so each stage lifts into its
own worker unchanged.

**What it is not.** Not a BL generator — the carrier issues the BL. Not an
auto-sender. Not a replacement for the documentation team; it is an exception
desk that turns 126 document checks into 25 decisions.

## Roadmap

Deliberately not built, in priority order: PDF extraction via Textract, which
recovers the 15 unreadable checks. An LLM adjudicator on Bedrock for the 11.9%
classifier residue and for extraction on documents the rules cannot parse. SI
generation from order data, closing the loop so the document the system authors
becomes the reference it later checks. Live Graph mailbox ingestion. An Outlook
add-in, so the verification appears beside the email the clerk is already
reading. Delivery orders and destination-side documents.

## Running against the organizers' server

`MailSource` covers both sources, so the same command works:

```bash
python run.py --source http://localhost:8080
```

To produce the alternative submission described in
[docs/assumptions.md](docs/assumptions.md):

```bash
python run.py --chase-as-comparison --out out/alt
```

## Layout

```
src/sdoc/
  mailsource.py   MailSource interface, bundle and HTTP implementations
  documents.py    attachment text extraction, document-type identification
  fields.py       the seven fields, label alignment, evidence capture
  normalize.py    per-field normalization and equality
  compare.py      verdicts and escalation precedence
  classify.py     stage-1 triage
  shipment.py     OC / booking reference threading
  pipeline.py     orchestration, submission and results output
  validate.py     submission shape and consistency checks
tests/            124 tests
eval/             mutation.py, audit.py
docs/             assumptions.md
```

Python 3.12. Dependencies: `openpyxl` and `python-docx` for spreadsheet and
Word attachments, `pytest` for the tests. The text path is stdlib only.
