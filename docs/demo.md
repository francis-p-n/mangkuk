# The 45-second demo

One shipment, one problem, one fix. No feature tour — a judge who has watched
eleven demos remembers a story, not a list.

## Before you record

```bash
python run.py && python tools/demo_data.py     # the 520-email run
python tools/thread_demo.py                    # the constructed thread
python run.py --source data/thread-demo --out out/thread \
              --sample data/thread-demo/sample_submission.json
```

Load the 520-email run, and have the thread ready to load between takes if you
want the folder shot. Open two tabs: **Today**, and the shipment file for
`5UHG-21401`.

Say "constructed" out loud when the twelve-email file is on screen. It is one
word, it costs two thirds of a second, and it is the difference between a judge
trusting the rest of the demo and wondering what else was staged.

---

## The script

**0:00–0:07 — the problem, on screen, no preamble**

> *Today: 129 drafts from 520 emails.*
> "Every container that ships gets a draft bill of lading, and someone checks
> it by eye against the instruction that ordered it. This desk had five
> hundred and twenty emails this morning."

*Screen: Today. The headline reads 66 shipments need you today.*

**0:07–0:15 — what the checking bought**

> "Sixty-six need attention. The other sixty-three match on every detail and
> nobody has to open them."

*Scroll once, slowly, so the queue and the three severity bands are visible.*

> "And they're in order of what it would cost: thirteen where the wrong party
> could take the cargo, first."

**0:15–0:27 — open one, and show the evidence**

*Click the top row: Linden & Hale Paper Limited.*

> "Consignee and notify party disagree between the instruction and the draft.
> Not 'the draft is wrong' — we can't know which side is stale, so it says
> what it found."

*Point at the comparison table — the two red rows against five green.*

> "Seven details, every one quoted from the document it came from, with the
> line it was on. Nothing here is a guess."

**0:27–0:36 — the thing they actually do next**

*Click "Write the email to the carrier".*

> "And the correction email is already written — quoting both documents, asking
> which is right rather than telling them. The clerk sends it themselves.
> Nothing goes out of this system automatically."

*Let the draft sit on screen for two full seconds. It is the strongest frame.*

**0:36–0:45 — the part that is the actual product**

*Switch to the twelve-email shipment file.*

> "And it's one folder per shipment — this is constructed data — booking,
> instruction, three drafts, the invoice, the arrival notice. The first
> correction only fixed one of the two problems. The second fixed the other."

*The folder header reads Corrected.*

> "So the shipment closes itself. That's the job."

---

## What not to say

**Don't claim it works on any shipping documents.** It degrades honestly on
unfamiliar paper — `eval/unseen.py` reads 30 of 35 fields on five shipments
written to share nothing with the bundle, and judged **zero** of them wrongly.
That is a better claim and it is true: *unfamiliar wording escalates rather
than being guessed at.*

**Don't oversell the AI.** The comparison is deterministic and that is the
selling point — same documents, same answer, every rule inspectable. The model
runs only where the parsers cannot read a document, it may only point at a
value already written there, and 62 tests hold it to that. A judge who thinks
this is an LLM wrapper will test it like one.

**Don't show the graph view.** On the supplied bundle it is five hundred and
twenty disconnected dots, because no reference in it appears twice. The
architecture is right and the sample data cannot show it. Say that if asked —
it is a more interesting answer than a picture.

## If you have thirty seconds more

The numbers that survive scrutiny, in order of how much they buy you:

- **602 defects injected, 602 caught, zero collateral flags.** No ground truth
  ships with the bundle, so the harness makes its own: take a pair the
  pipeline calls clean, inject a known defect, check it reports exactly that
  field and nothing else. Plus 63 unmutated controls that must stay silent.
- **31 real-world document quirks, 0 false alarms.** `21.577,00 KG` against
  `21,577 KG` is the same weight; `21,577 KG` against `21,577 MT` is a
  thousandfold error.
- **Everything the README claims is re-checked by `eval/rubric.py`**, which
  reads its thresholds out of `docs/validation.md`. The claims cannot drift
  from the code, because one of them is generated from the other.
