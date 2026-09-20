# SDOC — shipping document verification

Reads a shipping operations inbox, works out what each message is, and for
every draft Bill of Lading checks it against the Shipping Instruction that
authorised it — field by field, with the source lines attached so a person can
check the machine rather than trust it.

Built for the Averis hackathon against the supplied 520-email bundle.

## What it does, in plain terms

*No technical background needed for this section.*

When a shipping team sends a carrier a **shipping instruction**, the carrier
sends back a **draft bill of lading** to be approved. Someone has to read both
documents and check they say the same thing. It is slow, it is repetitive, and
missing one wrong detail means an amended bill, a delay, and rework.

This does that checking, and shows its working.

**It sorts the inbox.** 520 emails arrive as one pile — document checks,
requests for new instructions, invoice questions, operational updates and
spam. Each one is put in the right category, so nothing waiting to be checked
gets buried.

**It reads the attachments — whatever form they arrive in.** Plain text, Excel,
Word and PDF. If an attachment genuinely cannot be opened, it says so instead
of pretending.

**It compares seven details** on every shipment: shipper, consignee, notify
party, loading port, discharge port, number of containers, and gross weight.

**It understands that the two documents use different words for the same
thing.** One says `Port of Loading`, the other says `Load Port`. One says
`Consignee`, the other says `To the Order of`. It matches by meaning, not by
matching the labels.

**It catches the traps a tired person misses.** A port name changed while the
port code stayed the same. Four containers on the draft where the instruction
said three. A weight quoted in tonnes on one document and kilograms on the
other. A "bill of lading" that is actually a packing list.

**It does not make things up.** When a document is missing, unreadable, or the
wrong document entirely, it stops and says exactly why, rather than guessing.
Roughly one shipment in six comes back as "a person needs to look at this,
and here is the reason".

**It shows you the proof.** Every mismatch displays the wording from both
documents, with the line it came from. You are never asked to take the
computer's word for it — which matters, because you cannot email a carrier
saying "the software says you are wrong".

**It writes the correction email for you — and never sends it.** You read it,
change what you like, and send it from your own mailbox.

### What it found in the sample inbox

Of 129 document checks: **46 drafts had a real error** that would have gone to
the carrier, **63 were correct**, and **20 needed a human**. That is 85 in
every 100 decided without anyone reading a document — and, more to the point,
46 mistakes caught before they became someone's problem.

### How much of this is guesswork

Very little, deliberately. The part that decides whether two values match is
ordinary, predictable logic — the same input always gives the same answer, and
every rule can be inspected. AI is used only for the small number of documents
laid out in a way the rules do not recognise, and even then it is only allowed
to *point at* a value already written in the document. It is never allowed to
invent one. That restriction is enforced and tested.

The checking has been tested by deliberately corrupting 602 correct documents
and confirming every single error was caught, and against 31 real-world
document quirks — European number formats, company names written five
different ways, port aliases — with no mistakes in either direction.

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

```bash
python ui/build.py
```

`ui/build.py` writes `out/site/` — a three-page static site that uploads to
S3 unchanged. No server, no build tooling, no framework, no dependencies at
all in the browser.

| Page | What it is |
|---|---|
| `index.html` | Sign in |
| `welcome.html` | Four-step walkthrough, shown once |
| `checks.html` | The board, with the run's results inlined |
| `app.css` | Shared styles |

Publish it with `./deploy.sh <bucket-name> [region]`, which creates the
bucket, turns on website hosting, and uploads the four files with sensible
cache headers. It needs the AWS CLI and credentials.

Two things the script says out loud, worth repeating here. It makes the
bucket **publicly readable**, and `checks.html` carries the whole run inlined
— consignee names, addresses, ports, weights and OC numbers. Fine for a
hackathon demo, not fine for client data. And S3 website endpoints are
**HTTP only**; put CloudFront in front for `https://`.

**The sign-in is a demo, and says so on the page.** It accepts any email and
any password, checks nothing, and stores no password — it only remembers a
display name for the session. The route guard on `checks.html` is a front
door, not security: it keeps the prototype's flow coherent, and a real
deployment authenticates before the page is ever served (Cognito, or Entra ID
alongside the Graph app registration already needed for mail). That is the
one place where this prototype should not be mistaken for a product.

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
its word; see below.

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

The same agent decides the classifications the rules abstain on — 153 of 520
emails, including the 91 draft-chasers discussed in
[docs/assumptions.md](docs/assumptions.md), which it judges individually rather
than by a blanket flag.

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
spotted; see *Unfilled forms are not values* below.

Defects found, by field: container count 19, port of discharge 13, gross
weight 12, notify party 8, consignee 7, shipper 7, port of loading 6.

## The workspace

The unit on screen is a shipment, not an email, and the language is the desk's
rather than the pipeline's — "needs correction", "needs a person", "clear".

Three piles, so a clerk's job becomes working the middle one. Four pickers
narrow the list the way the desk actually thinks — **customer**, **their
country**, **shipping from** and **going to** — and they cascade: choosing
Australia leaves only the customers and destinations that still have
shipments, so no combination ever comes back empty. Free-text search covers
customer, country, address, OC number, port, vessel and cargo. Selecting a
shipment shows its route, cargo, product and carrier, then the seven fields as
the shipping instruction states them beside the draft, with conflicts
highlighted and the source label under every value — so it is visible that the
BL said `To the Order of` where the instruction said `Consignee`.

"Show the lines it read" opens the raw source lines with their line numbers.
That is the glass box, one click deep, out of the way until wanted.

"Draft correction reply" produces a ready email quoting both values per
conflicting field. Nothing is sent — the draft is shown, the clerk sends it.

New users land on a four-step walkthrough: the two documents and the seven
details, the three piles, how to read a mismatch (with a worked example), and
the promise that nothing is ever sent for them. It is skippable, shown once,
and reachable again from the header — and finishing it also settles the
inline explainer on the board, so nobody reads the same thing twice.

Escalations name their reason in plain language and say that the system stopped
rather than guessed. Where a document could not be read there is no extracted
consignee, so the row falls back to the email's own subject instead of
presenting a nameless shipment.

Everything renders from `out/results.json`. There is no backend, no database
and no authentication, which is deliberate: one static file has no deployment
that can fail during a demo.

## Testing and validation

There is no ground truth in the bundle, so accuracy is established six ways.

### 1. Test suite — 237 tests, all passing

```
237 passed in 1.35s
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

### 2. Defect injection — 602 injected, 100% caught

`eval/mutation.py` takes every pair the pipeline calls clean, injects one known
defect into the draft BL, and checks that exactly that field is reported.

```
clean pairs available as mutation hosts: 63
injected defects : 602
caught           : 602  (100.0%)
caught cleanly   : 602  (100.0% - no collateral fields)
control failures : 0
```

Ten injection strategies across the seven fields, including the two subtle
ones: a port where only the UN/LOCODE is wrong while the city still reads
correctly, and a container spec where the count is right but the box type
changed. Every one was caught, none produced a collateral false flag on another
field, and the unmutated control run stayed silent.

### 3. No-ground-truth audit

`eval/audit.py` asks where the system could be wrong.

**Normalization sensitivity.** The overwhelming majority of field agreements
are byte-identical strings; normalization decides a handful — thousands
separators (`243588` vs `243,588`) and ports where one side omits the
UN/LOCODE. Every one was inspected by hand. The comparator is doing very
little quiet work, which is the point.

**Classifier residue.** 62 of 520 emails (11.9%) fall through every rule to the
default. These are the genuine judgement calls — RPA billing notifications,
berthing reports, a time-off request — and they are precisely the residue an
LLM stage should own. Rules handle 88.1% at high confidence.

**Unmapped labels.** Every label in the corpus that maps to no field was
reviewed. All are legitimately outside the seven — freight terms, HS codes,
vessel and voyage, booking references.

### 4. The constructed edge-case block resolves 5/5/5/5

Emails 501-520 are not ordinary traffic: they are a built set of escalation
cases, five for each reason. Landing exactly five `wrong_doc_type`, five
`missing_attachment`, five `unreadable` and five `missing_value` is the
closest thing to a ground-truth check the bundle allows, and it is pinned as a
test.

Getting there exposed two real defects.

**Unfilled forms are not values.** Two instructions arrived with the blanks
still in them — `Port of Loading (POL): ____MT` and `PORT OF DISCHARGE: TBA`,
sitting directly above `NET WEIGHT: _______ MTS`. The comparator read `____MT`
as a port and reported it as a discrepancy against the carrier's `SINGAPORE
(SGSIN)`. That is a false alarm of the worst kind: it would have sent a clerk
to argue with a carrier about a detail their own side had never filled in.
Placeholder tokens — runs of underscores or question marks, `TBA`, `TBC`,
`N/A`, `NIL`, `PENDING` — now count as absent, so the shipment escalates as
`missing_value` instead.

**Three explicit comparison requests were being filed as general mail.** They
read *"Please compare the SI and draft BL ... (attachments appear to have been
dropped)"* — a comparison asked for outright, with the files lost in transit.
The classifier had no phrase for that wording, so they never reached the
checking stage at all. They are now `BL_COMPARISON` with
`missing_attachment`, which is what the block was built to test.

Worth noting what this *did not* change: those three are a distinct template
from the 91 draft-chasers in [docs/assumptions.md](docs/assumptions.md). The
organizers built exactly five `missing_attachment` cases, not ninety-six,
which makes the case for leaving the chasers as general mail stronger than it
was before.

### 5. Clerk's-eye cases — 31 real-world variations, 0 missed

The bundle is one generator's idea of how documents vary. A real desk sees
more. `eval/desk_cases.py` encodes what an experienced clerk would say about
31 variations and holds the comparator to it, weighting the two directions of
error very differently: a false alarm costs minutes, a miss puts a wrong value
on a bill of lading.

The first run passed 19 of 29 with **0 misses and 10 false alarms** — every
one a case a clerk would wave through. Fixing them changed nothing about the
bundle's results (still 63/48/15), which is the point: these were real-world
robustness gaps, not bundle bugs.

What it found, and what now works:

- **European decimal commas.** `21.577,00 KG` and `21,577 KG` are the same
  weight. Roxcel is in Vienna.
- **Tonnes.** `132 MT` equals `132,000 KG`. Previously flagged. Meanwhile
  `21,577 KG` against `21,577 MT` is a 1000x error and must be caught — it is.
- **Genuinely ambiguous numbers escalate.** `21.577` is 21577 to a German
  forwarder and 21.577 to everyone else. Where two readings disagree on the
  verdict, a person decides rather than the parser guessing.
- **"ton" is refused.** Short, long and metric tons differ by up to 12%, so
  the field becomes undecidable rather than converted.
- **Box-type synonyms.** `GP`/`DV`/`DC` all mean a standard dry box; `HC`,
  `HQ` and `HIGH CUBE` all mean high cube. `FCL` is deliberately *not*
  aliased — it describes the load, not the box.
- **Punctuated legal forms.** `Roxcel Trading G.m.b.H.` is `ROXCEL TRADING
  GMBH`; `L.L.C.` is `LLC`; `BALL & DOGGETT` is `BALL AND DOGGETT`.
- **Port aliases.** A terminal named on one document only (`PORT KLANG
  (WESTPORT)`), an official name beside a common one (`JAWAHARLAL NEHRU
  (NHAVA SHEVA)`), and spelling drift (`KLANG`/`KELANG`) all read through.
  Country and UN/LOCODE stay exact, so `MOMBASA, KENYA (KEMBA)` against
  `TUTICORIN, INDIA (KEMBA)` still conflicts.

The cases run as part of the suite, so none of this can silently regress.

### 6. The agent's guardrails are tested, the live call is not

27 tests drive the resolver through a fake client: a grounded value is
accepted, an invented company is rejected, a genuine quote carrying a smuggled
value is rejected, an implausible weight is rejected, a field the parser
already found is never overwritten, malformed and empty replies are treated as
abstention, and a transport failure is recorded without breaking the run. Three
cascade tests prove the placement: a recovered field can turn an escalation
into a clean pass, can equally reveal a defect, and a hallucinating agent still
escalates.

**Not verified:** no live call has been made. There are no AWS credentials in
this environment, so the Bedrock path is exercised only up to authentication —
imports resolve and the client constructs, then the call fails and is recorded
as a note. The prompt and the model's real behaviour are unmeasured. With the
agent misconfigured the pipeline still produces a byte-identical valid
submission, which is the property that matters most for demo day.

### Known limits

Five PDFs have no extractable text at all — a corrupt cluster that reports
`EOF marker not found` — and escalate as `unreadable`. OCR is the only route
to those, and a declared-unreadable document is a correct answer where a
hallucinated one is not. The largest open question is documented in
[docs/assumptions.md](docs/assumptions.md) — 91 emails chasing a draft BL are
currently GENERAL, and `--chase-as-comparison` flips them.

## Business viability

**What it replaces.** A clerk opening two attachments and eye-comparing seven
fields. Assuming five minutes per check — an estimate to confirm with the
operations team, not a measured figure — the 126 checks in this batch are about
**10.5 hours** of desk time.

The system decides 111 of them outright and escalates 15 with the reason
already stated. At roughly two minutes to action a pre-diagnosed escalation,
that is about **30 minutes of human time**, against 10.5 hours. The saving is
in the same order as the work itself, and it scales with volume rather than
headcount.

**Where the money actually is.** Not the minutes — the 48 defective drafts
caught before release. A wrong consignee or port on a released BL means an
amendment fee, a delayed release, and in the worst case cargo moving against a
document naming the wrong party. Catching those is worth more than the clerical
time, and the system caught them at a rate of 43.2% of decided checks.

**Why an ops team would actually use it.** The unit on screen is a shipment,
not an email. The vocabulary is "needs correction", not `MISMATCH`. Every flag
shows both values and the labels they came from, so the correction email
writes itself and the clerk stays accountable for sending it. Nothing is
auto-sent.

**Adoption risk, handled.** The system never guesses. 11.9% of checks come back
as "a person needs to look at this, and here is exactly why". A tool that
silently guessed on those would be abandoned the first time it was wrong on
something expensive.

**Deployment shape.** Graph change notifications into API Gateway and Lambda,
S3 for raw documents, Step Functions per email so a throttle retries one stage
rather than the batch, Bedrock over a VPC endpoint so document text never
leaves the tenant, DynamoDB keyed on OC number, static front end on S3 and
CloudFront, corrections written back as Outlook drafts rather than sent. Full
diagram, security posture and costs in [docs/architecture.md](docs/architecture.md).

**What it is not.** Not a BL generator — the carrier issues the BL. Not an
auto-sender. Not a replacement for the documentation team; it is an exception
desk that turns 126 document checks into 25 decisions.

## Roadmap

### Completing the build

PDF extraction via Textract, which recovers the 15 unreadable checks. An LLM
adjudicator on Bedrock for the 11.9% classifier residue and for extraction on
documents the rules cannot parse. Live Graph mailbox ingestion, replacing the
bundle behind the existing `MailSource` interface. An Outlook add-in, so the
verification appears beside the email the clerk is already reading rather than
asking anyone to leave their inbox.

### Multi-document consistency

The same shipment produces more than two documents. Averis's shipping
documentation service prepares the commercial invoice, packing list,
certificate of origin, shipment advice and the export permit declaration for
Singapore and Malaysia, alongside the Bill of Lading received from the freight
forwarder and carrier. All of them carry overlapping fields — parties, ports,
weights, container counts — and all of them have to agree.

This is a loop, not a redesign. `compare_fieldsets` takes two field sets and
does not care which documents produced them, so extending to "compare every
document in the set against the SI as reference" reuses the comparator, the
normalization rules and the evidence model unchanged. The three decoy
attachments already in the corpus — a packing list, a certificate of origin and
a commercial invoice — are exactly the documents this would cover, which is
why they are identified by type today rather than merely rejected.

The cost of error also rises here. A wrong field on an export permit
declaration is not rework; it is an incorrect filing to a customs authority.

### Letter of credit discrepancy checking

The highest-value extension, and structurally the same problem. Averis already
offers "LC Checking - Administration of LCs, including validation of LC
policies and requirements, handle and resolve LC discrepancy" as part of this
service line.

An LC states required terms; the presented document set must match them;
discrepancies have to be found before presentation. That is this engine with a
different reference document — check against a source of truth, surface
conflicts field by field with both values quoted, escalate what cannot be
decided rather than guessing.

The stakes are an order of magnitude higher than a draft BL. A BL mismatch
costs an amendment and a delay. An LC discrepancy means the bank refuses the
presentation: a discrepancy fee, and payment held until it is resolved. The
same escalation discipline matters more, not less, when the alternative to
"a person needs to look at this" is a rejected presentation.

### Deferred, and why

SI generation from order data would close the loop, so that the document the
system authors becomes the reference it later checks. It is deferred rather
than dismissed: party and port details must come from customer master data,
which the bundle does not supply, and generating them from anything less is how
a shipment gets sent to an address that never existed.

Delivery orders and destination-side documents are out of scope because nothing
in the supplied corpus sits downstream of the carrier. Authentication and
multi-tenancy are out of scope for a hackathon build.

Auto-sending correspondence is out of scope permanently. The system drafts, a
person sends.

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
  agents.py       the LLM recovery stage and its grounding checks
  places.py       one settled spelling per port, countries from addresses
  labels.py       the shared vocabulary for categories, statuses and fields
  pipeline.py     orchestration, submission and results output
  validate.py     submission shape and consistency checks
ui/
  index.html      sign in
  welcome.html    first-run walkthrough
  checks.html     the board, with a data placeholder
  app.css         shared styles
  build.py        assembles out/site/
tests/            237 tests
eval/             mutation.py, audit.py, desk_cases.py
docs/             assumptions.md, architecture.md
```

Python 3.12. Dependencies: `openpyxl` and `python-docx` for spreadsheet and
Word attachments, `pytest` for the tests. The text path is stdlib only.
