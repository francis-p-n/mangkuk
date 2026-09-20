# SDOC — shipping document verification

Reads a shipping operations inbox and checks every draft Bill of Lading
against the Shipping Instruction that authorised it — field by field, showing
the source lines so a person can check the machine rather than trust it.

Built for the Averis hackathon against the supplied 520-email bundle.

---

## 1. For the judges

**The problem.** A documentation desk gets one inbox: document checks, new
instruction requests, invoice questions, operational mail and spam. For each
check, someone opens two attachments and compares seven fields by eye. Slow,
repetitive, and a missed detail means an amended bill and a delay.

### What it does

- **Sorts 520 emails** into five categories, so nothing waiting to be checked
  gets buried.
- **Opens any attachment** — plain text, Excel, Word and PDF.
- **Compares seven fields**: shipper, consignee, notify party, loading port,
  discharge port, container count, gross weight.
- **Matches by meaning, not by label.** One document says `Port of Loading`,
  the other `Load Port`; one says `Consignee`, the other `To the Order of`.
  66 distinct labels appear across the corpus for these seven concepts.
- **Catches the subtle traps**: a port name changed while its UN/LOCODE stayed
  the same, tonnes against kilograms, four containers where the instruction
  said three, a "bill of lading" that is really a packing list.
- **Refuses to guess.** Missing, unreadable or wrong document → it stops and
  says exactly why.
- **Shows its evidence.** Every mismatch quotes both documents, with line
  numbers.
- **Drafts the correction email, and never sends it.**

### What it found

| | |
|---|---:|
| Emails triaged | 520 |
| Document checks | 129 |
| Drafts with a real error, caught | **46** |
| Drafts clean | 63 |
| Handed back to a person | 20 |
| **Decided without a human** | **84.5%** |

### Why you can believe it

**The comparison uses no AI.** It is ordinary deterministic code: same input,
same answer, every rule inspectable. An LLM is used only for documents the
parsers cannot read, and even then it may only *point at* a value already in
the document — never invent one. That restriction is enforced and tested.

No ground truth ships with the bundle, so accuracy is established six ways.

**1 — Test suite: 249 passing.** Every normalization rule, every label alias,
document identification across `.txt`/`.xlsx`/`.docx`/`.pdf`, all four
escalation reasons and their precedence, the classifier, and submission
validation. 18 cases are pinned after hand-reading both source documents: 7
known defects with their exact field lists, 3 clean drafts, 8 escalations.

Two traps are pinned because a naive implementation gets them wrong:
`Notify Party/Intermediate Consignee` contains both words and must resolve to
notify party; `NET WEIGHT` must never be read as gross weight.

**2 — Defect injection: 602 injected, 602 caught.**

```
clean pairs used as hosts : 63
injected defects          : 602
caught                    : 602  (100.0%)
caught cleanly            : 602  (100.0% - no collateral field flagged)
control failures          : 0
```

Ten injection strategies, including the two subtle ones: a port where only the
UN/LOCODE is wrong while the city still reads correctly, and a container spec
where the count is right but the box type changed.

**3 — Clerk's-eye cases: 31 variations, 0 missed, 0 false alarms.** The bundle
is one generator's idea of how documents vary; a real desk sees more. The
first run scored 19/29 with **0 misses but 10 false alarms** — every one a
case a clerk would wave through. All are now handled:

| Variation | Verdict |
|---|---|
| `21.577,00 KG` vs `21,577 KG` | same weight (European decimals) |
| `132 MT` vs `132,000 KG` | same weight |
| `21,577 KG` vs `21,577 MT` | **conflict** — 1000× apart |
| `21.577 MT` vs `21,577 KG` | undecidable — readings disagree, escalate |
| `21,577 TONS` | undecidable — short, long and metric differ |
| `10 x 20'GP` vs `10 x 20'DV` | same box type |
| `Roxcel Trading G.m.b.H.` vs `ROXCEL TRADING GMBH` | same company |
| `BALL & DOGGETT` vs `BALL AND DOGGETT` | same company |
| `PORT KLANG (WESTPORT)` vs `PORT KLANG` | same port |
| `MOMBASA, KENYA (KEMBA)` vs `TUTICORIN, INDIA (KEMBA)` | **conflict** |

Fixing them changed nothing about the bundle's results, which is the point:
these were real-world robustness gaps, not bundle bugs.

**4 — The constructed edge-case block resolves 5/5/5/5.** Emails 501–520 are a
built set of escalation cases — five `wrong_doc_type`, five
`missing_attachment`, five `unreadable`, five `missing_value`. Landing exactly
on that split is the closest thing to a ground-truth check the bundle allows,
and it is pinned as a test. Getting there exposed two real defects:

- Two instructions arrived with the blanks unfilled — `Port of Loading (POL):
  ____MT`, `PORT OF DISCHARGE: TBA` — and were being reported as discrepancies
  against the carrier's real ports. That would send a clerk to argue with a
  carrier about a field their own side never filled in.
- Three emails saying *"Please compare the SI and draft BL (attachments appear
  to have been dropped)"* were filed as general mail and never reached the
  checking stage.

**5 — No-ground-truth audit.** Of all field agreements, the overwhelming
majority are byte-identical strings; normalization decides only a handful
(thousands separators, a port missing its UN/LOCODE), and every one was
inspected by hand. 59 of 520 emails (11.3%) fall through every classifier rule
to the default, and a further 91 are the draft-chasers held deliberately at low
confidence while that question is open — 150 in total (28.8%). Those are the
genuine judgement calls, and exactly the residue an LLM stage should own. The
remaining 71.2% are decided by rules at high confidence.

**6 — The agent's guardrails are tested; the live call is not.** 39 tests drive
the resolver and the provider wiring through a fake client: a grounded value is accepted, an invented
company rejected, a genuine quote carrying a smuggled value rejected, an
implausible weight rejected, malformed replies treated as abstention, and a
hallucinating agent still escalates. **Not verified:** no live model call has
been made, so the prompt's real behaviour is unmeasured. With the agent
misconfigured the pipeline still produces an identical valid submission.

### Known limits

Five PDFs have no extractable text at all — a corrupt cluster reporting `EOF
marker not found` — and escalate as `unreadable`. OCR is the only route to
those, and a declared-unreadable document is a correct answer where a
hallucinated one is not.

The largest open question is documented in
[assumptions](docs/assumptions.md): 91 emails chasing a draft BL are
classified as general mail, and `--chase-as-comparison` flips them.

More: [validation](docs/validation.md) · [pipeline](docs/pipeline.md) ·
[the site](docs/site.md) · [architecture](docs/architecture.md) ·
[business case](docs/business-case.md) · [open assumptions](docs/assumptions.md)

---

## 2. Usage

Python 3.12, then `pip install -r requirements.txt`.

```bash
python run.py
```

Reads `data/`, writes `out/submission.json` (the scored file) and
`out/results.json` (everything a human needs).

```bash
python ui/build.py
```

Builds the site into `out/site/` — five pages, no framework, no browser
dependencies.

### Everything else

| Command | What it does |
|---|---|
| `python -m pytest tests -q` | 249 tests |
| `python eval/mutation.py` | Inject defects, measure detection |
| `python eval/desk_cases.py` | 31 real-world document quirks |
| `python eval/audit.py` | Audit a run with no ground truth |
| `python eval/score.py --truth gt.json` | Score against the organizers' truth |
| `python run.py --source http://host:8080` | Run against their server |
| `python run.py --agent bedrock` | Turn the LLM recovery stage on |
| `python tools/demo_data.py` | Scramble the data for public sharing |
| `./deploy.sh <bucket>` | Publish to S3 |

Agent providers: `bedrock` (keeps document text inside the tenant),
`anthropic`, `gemini`. Default is `off`, so the scored run stays
deterministic.

---

## 3. Real usage

**A clerk opens Today.** It says one thing: *46 drafts have something that
needs fixing. 20 need you to look. The other 63 match on every detail.* Two
queues, nothing else — no filters, no browsing.

**They open the first.** Shipment `5ALT-01226`, six 40ft high-cube containers
of coated ivory board, Nantong to Karachi. Two details flagged: consignee and
notify party. The instruction names one company, the carrier's draft another
— and the draft calls the field *To the Order of* where the instruction called
it *Consignee*.

**They check the working.** "Show the exact wording on both documents" prints
both source lines with line numbers. Nothing is taken on trust.

**They send the correction.** One click writes the email quoting both versions
of both fields. They read it, edit it, send it from their own mailbox. Nothing
is ever sent automatically.

**Anything unclear is handed back, not guessed.** One shipment in six returns
*"the carrier sent a commercial invoice instead of a bill of lading"* or
*"a detail is blank on the instruction"* — the reason stated, so the clerk
knows what to do rather than merely that something failed.

**Search is a separate page**, for finding a specific shipment: filter by
customer, their country, export port or destination. The filters cascade, so
no combination comes back empty.

### Assumed, not measured

Five minutes per manual check — worth confirming with the operations team. On
that assumption these 129 checks are about 10.5 hours of desk time, against
roughly 30 minutes reviewing pre-diagnosed escalations. The real value is the
46 wrong drafts caught before they reached a carrier.

---

## Layout

```
src/sdoc/
  mailsource.py   where email comes from (bundle, HTTP, a real mailbox)
  documents.py    attachment text and document-type identification
  fields/         getting the seven fields out, with evidence
  normalize/      whether two values mean the same thing, one file per type
  compare.py      verdicts and escalation precedence
  classify.py     stage-1 triage
  agents/         the LLM stage: clients, prompts, resolver, triage
  places.py       one settled spelling per port
  labels.py       the shared vocabulary
  pipeline.py     orchestration
tests/          249 tests
eval/           mutation, desk cases, audit, scorer
ui/             the site: pages, shared lib/, and its build
tools/          data scrambler for public demos
docs/           validation, pipeline, architecture, business case, assumptions
data/           the supplied bundle
```

`normalize/` and `fields/` and `agents/` are packages rather than single
files: each has one module per thing that changes for its own reason — a
field type, a reading pass, an LLM provider. Import paths are unchanged, so
adding a provider or a compared field is a new file, not a new branch in a
growing function.
