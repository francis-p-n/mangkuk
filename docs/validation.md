# How the accuracy was established

No ground truth ships with the bundle, so correctness is shown ten ways.
Every number here is reproducible from the commands in the README.

## The claims

These are the numbers this document backs up, and the numbers
`python eval/rubric.py` holds the project to. Change one here and the check
starts enforcing the new value - they cannot drift apart, because there is
only one place they are written.

| Claim | Value |
|---|---|
| tests passing | 498 |
| defects injected | 602 |
| defects caught | 602 |
| desk cases | 31 |
| desk cases missed | 0 |
| desk cases false alarms | 0 |
| edge block split | 5/5/5/5 |
| classifier residue | 0 |
| corpus emails | 520 |
| agent guardrail tests | 62 |
| unseen cases | 5 |
| unseen fields read | 30 |
| unseen defects invented | 0 |
| unseen defects waved through | 0 |
| grouping tests | 29 |
| classification templates | 33 |
| classification labelled | 520 |
| classification disagreements | 0 |
| split templates | 0 |
| classifier mutants | 9 |
| classifier mutants killed | 9 |

## Testing and validation

There is no ground truth in the bundle, so accuracy is established ten ways.

### 1. Test suite — 498 tests, all passing

```
498 passed in 16.7s
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

`tests/test_agent_limits.py` covers the other half of that: what happens
when a provider will not answer. A run asks for 64 calls against the bundle,
and on a free tier most come back 429 - so the tests assert that a
rate-limited call is counted as silence rather than as the model abstaining.
Rehearsed end to end against a stand-in that throttles everything: 64 of 64
calls unanswered, submission byte-identical to the deterministic run, and the
run says so in as many words.

`tests/test_http_source.py` runs against a real socket rather than a mock,
because the failures that matter on the HTTP path are not in the documents:
a server that stalls, a 503 in the middle of 260 requests, a hostname that
resolves to a stack nothing is listening on.

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

**Classifier residue.** 0 of 520 emails now fall through to the default: every
template in the bundle is recognised by something it says. It was 59, and the
59 were RPA billing notifications, berthing reports and an office-hours notice
— operational mail that no rule named, so it arrived at GENERAL by exhaustion
rather than by evidence.

That distinction mattered more than it looks, and section 8 is the reason this
paragraph is no longer the headline. Residue is a coverage figure. It says how
much the rules will decide, not how much they decide correctly, and it is
one-sided: it only ever rose. Broadening a single invoice rule until 55
berthing reports and a time-off request were filed as invoice questions
*improved* it from 59 to 4 while leaving every test green. A number that
rewards a worse classifier is not evidence, and it is now reported next to one
that is.

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

### 7. Grouping — tested against the code that ships

`tests/test_grouping.py` used to carry its own copy of the union-find and
assert against that. The shipped grouping therefore had no coverage at all:
deleting bridging from `web/lib/graph.ts` - the one case its own comments
call out as the thing single-key grouping gets wrong - left all of the Python
tests green and `tsc --noEmit` clean. The copy had also drifted, having never
learned that a B/L number is an edge.

The rules now live in `web/lib/graph.ts`, which imports nothing, and 29 tests
run against it directly (`npm test --prefix web`, no framework - Node reads
the TypeScript). That same deletion now fails five of them. The Python suite
reaches the same module through `tools/group_cli.mjs`, so the corpus-level
claims - 520 files of one email each, nothing lost or duplicated, two
lookalike shipments kept apart - are made about the code that runs.

What this bought beyond coverage: the constructed thread folds to `OK` and
reads as corrected, which it could not do before. The fold dropped clean
checks before choosing the deciding email, so a file could only ever end on a
failure, and `resolved` was unreachable for every folder shape the pipeline
can emit.

### 8. Is the classifier right — 520 labelled, 0 disagreements

Every other check on this page measures the comparison stage. The classifier
had nothing measuring it at all: the only number anyone quoted was the
residue, which counts how much the rules will decide and says nothing about
whether they decide correctly. The gap was not theoretical. Adding three
plausible words to one invoice rule refiled 55 berthing reports, RPA
notifications and a time-off request as invoice questions — 432 tests still
passed, and the residue figure *improved* from 59 to 4.

Fixing that needs labels, and the bundle ships none. Labelling 520 emails by
hand is a day nobody has; labelling them with the classifier's own phrase list
only asks the classifier whether it agrees with itself.

**The corpus is written from templates, and a template is recoverable.** Strip
the security banner, the greeting, the quoted reply and the signature block;
keep the opening clause; replace every name, port, vessel, reference and
number with a placeholder. What is left is the sentence the template was built
from. `eval/fingerprint.py` does this and recovers **33 templates covering all
520 emails**, 2 of them singletons, none mixing two kinds of email.

So a person reads 33 exemplars and decides 33 times.
`eval/gold/clusters.json` records each decision with the exemplar it was read
from and a sentence of reasoning, so the judgement can be argued with rather
than taken on trust.

```
macro-F1              : 1.0000   (over 406 plainly-labelled emails)
accuracy              : 1.0000   (406/406)
templates split across categories : 0
```

Two rules the scorer keeps on itself. It will not score against a label nobody
was sure of — only rows at confidence 0.90 or above are used, and anything
lower counts against coverage rather than against the classifier. And it will
not let a judgement call flatter the result: two templates are marked
**contested** — the 91 draft-chasers, and 23 notes about a missing goods
receipt that block an invoice — because the taxonomy has two boxes that
genuinely fit. Those 114 emails are scored on their own line, not folded into
the headline.

**A second signal that needs no labels at all.** Emails written from one
template are one message, so a classifier that files them under two categories
is being decided by something that is not the message. That check found the
real bug: **subjects and bodies are drawn independently in this corpus** for
operational mail — `email_075` is headed "Time Off Request" over an RPA
billing notice, `email_021` is headed "_RPA_ India HSS SD Billing Process
Completed" and asks for shipping instructions. The classifier read the subject
alongside the body, so seven templates split down the middle: 94 emails
written from the same sentence, filed under two categories depending on which
heading the generator had stapled on.

Three changes followed, and all three are the same change: **the message
decides.** The body is matched first and the subject only votes when the body
is silent (which is the eleven messages here that have no body at all).
Operational traffic — berthing reports, outstanding-BL worklists, loading
updates, robot notifications — is recognised by what it says instead of
arriving at GENERAL by exhaustion. And the body is flattened before matching,
because a mail client that hard-wraps at 72 characters puts a newline through
the middle of "query on invoice" and nothing in this corpus wraps.

### 9. Would the harness notice — 9 live mutants, 9 killed

An accuracy of 1.0000 against labels is worth exactly as much as the harness's
ability to fail. `eval/classifier_mutation.py` applies fourteen realistic
regressions to the live rules and asks, of each, whether the checks go red.

```
mutants                : 14
changed an answer      : 9  (5 changed none, so there was nothing to catch)
killed                 : 9/9
the old residue check  : 7/9
```

Five mutants are *equivalent*: they rewrite a rule that cannot matter because
something earlier already decided. Deleting every spam phrase changes no
answer in this corpus, because spam is caught entirely by the sender domain
list — worth knowing on its own, since it means one list is doing all of that
work. Counting those as survivors would understate the harness and counting
them as kills would flatter it, so they are reported apart from both.

The old residue check kills 7 of the 9. The two it misses are the two that
matter most: both make the rules decide *more*, and wrongly, which the residue
figure reads as an improvement.

### 10. Documents the bundle never contained — 5 cases, 0 judged wrongly

Every other check here measures the checker against the supplied corpus, which
cannot tell a system that has learned the shipping framework from one that has
learned this bundle's habits. `eval/unseen.py` measures the difference: five
shipments written to share nothing with the pack — Brazilian coffee to Hamburg,
Korean steel to Houston, Dutch bulbs to Santos, Indian textiles to Felixstowe,
Chilean wine to Yokohama — with unfamiliar companies, lanes, commodities,
numeric conventions and label wording.

Two numbers, and they are not the same number.

**Read** is vocabulary: 30 of 35 fields. The five misses are all one document,
a shipping instruction labelled `Receiver`, `From Port`, `To Port`, `Total
Gross` and `Units` — ordinary shipping English the alias table has not got.
That costs a comparison and escalates the email.

**Wrong** is judgement: a defect invented, or a real one waved through. Zero of
each. The planted defects in fields it could read — a one-tonne weight error
and a discharge port whose city is right and whose UN/LOCODE is wrong — were
both caught, and the deliberate rewrites were not flagged: `B.V.` against `BV`,
`41.250,00 KG` against `41,250 KG`, `40'HC` against `40'HIGH CUBE`.

The document it could not read returned `NEEDS_REVIEW` with no defects at all.
That is the behaviour worth having: a system fitted to the corpus would have
invented comparisons out of half-parsed text, and this one escalated.

What this does *not* show is that the vocabulary is complete. It is sized to
the corpus, and unfamiliar wording escalates rather than being guessed at —
which is also what the LLM resolver exists to close.

