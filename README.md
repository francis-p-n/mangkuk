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

- **249 tests** pass, including 18 hand-verified cases pinned as regressions.
- **602 defects injected into clean documents — 602 caught**, none with a
  collateral false flag, and the unmutated control run stayed silent.
- **31 real-world document quirks** — European decimals, tonnes, `&` vs `AND`,
  port aliases — with **0 missed and 0 false alarms**.
- Emails 501–520 are a constructed edge-case block, five per escalation
  reason. The pipeline resolves it **exactly 5/5/5/5**.
- **The comparison uses no AI.** It is ordinary deterministic code: same input,
  same answer, every rule inspectable. An LLM is used only for documents the
  parsers cannot read, and even then it may only *point at* a value already in
  the document — never invent one. That restriction is enforced and tested.

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
src/sdoc/     the pipeline: mail source, extraction, comparison, agent
tests/        249 tests
eval/         mutation, desk cases, audit, scorer
ui/           the site and its build
tools/        data scrambler for public demos
docs/         validation, pipeline, architecture, business case, assumptions
data/         the supplied bundle
```
