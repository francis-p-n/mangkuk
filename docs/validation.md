# How the accuracy was established

No ground truth ships with the bundle, so correctness is shown six ways.
Every number here is reproducible from the commands in the README.

## Testing and validation

There is no ground truth in the bundle, so accuracy is established six ways.

### 1. Test suite — 309 tests, all passing

```
309 passed in 4.81s
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

Two more suites pin judgements rather than behaviour. `tests/test_severity.py`
asserts that the consequence ranking still says what an operations team was
told it says — that a wrong consignee outranks a wrong container count, and
that three cheap errors never add up to an expensive one. `tests/test_learned.py`
asserts mostly what a desk correction *cannot* do: reach a pair it was not
taught, reach another field, supply a value the parsers never found, or affect
a run that did not ask for it.

`tests/test_chasers.py` is a different kind of test: rather than pinning an
output, its 14 assertions pin the *corpus evidence* behind the draft-chaser
decision — that no chaser asks to compare, that all three hand-built
zero-attachment cases do, that a chaser's booking reference appears nowhere
else in 520 emails or any attachment. The argument in
[docs/assumptions.md](assumptions.md) cannot quietly stop being true.

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

**Classifier residue.** 59 of 520 emails (11.3%) fall through every rule to
the default. These are the genuine judgement calls — RPA billing
notifications, berthing reports, a time-off request — and they are precisely
the residue an LLM stage should own. Rules decide the remaining 88.7% at high
confidence.

The 91 draft-chasers used to sit in this residue too, held at low confidence
while the question was open. [docs/assumptions.md](assumptions.md) now settles
it on corpus evidence, so a rule decides them and the agent is never asked.

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
from the 91 draft-chasers in [docs/assumptions.md](assumptions.md). The
organizers built exactly five `missing_attachment` cases, not ninety-six —
and three of those five carry no attachment at all, which is what makes them
worth building. That became the first of the four arguments that settle the
chaser question in [docs/assumptions.md](assumptions.md).

### 5. Clerk's-eye cases — 31 real-world variations, 0 missed

The bundle is one generator's idea of how documents vary. A real desk sees
more. `eval/desk_cases.py` encodes what an experienced clerk would say about
31 variations and holds the comparator to it, weighting the two directions of
error very differently: a false alarm costs minutes, a miss puts a wrong value
on a bill of lading.

The first run passed 19 of 29 with **0 misses and 10 false alarms** — every
one a case a clerk would wave through. Fixing them changed nothing about the
bundle's results (still 63/46/20), which is the point: these were real-world
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

39 tests drive the resolver and the provider wiring through a fake client:
a grounded value is
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
hallucinated one is not. The largest classification call — 91 emails chasing
a draft BL — is resolved in [docs/assumptions.md](assumptions.md) and pinned
in `tests/test_chasers.py`; `--chase-as-comparison` still flips them.
