# What the hackathon asks for, and where each part is met

The brief ships as `data/README.md` in the participant bundle. This restates
it in full and pairs every requirement with the code that satisfies it and the
test that holds it there, so "did we actually do all of it" is a question with
an answer rather than a memory.

Where the brief is silent, that is recorded too — the silences are in
[assumptions.md](assumptions.md), and one of them is worth 30% of the score.

---

## 1. Classify every email

Each of the 520 emails gets exactly one category:

| Category | What it is |
|---|---|
| `BL_COMPARISON` | a draft bill of lading to check against its instruction |
| `SI_REQUEST` | preparing, requesting or submitting a shipping instruction |
| `INVOICE_QUERY` | an invoice, freight charge or billing question |
| `GENERAL` | operational traffic — vessel updates, reports, reminders |
| `SPAM` | unsolicited mail, phishing and scams |

Met by [`classify.py`](../src/sdoc/classify.py). Rules first, with the LLM
stage taking only what the rules abstain on.

## 2. Compare the two documents

For every `BL_COMPARISON`, compare the **Shipping Instruction** against the
**draft Bill of Lading** and report one of three outcomes:

| Status | When |
|---|---|
| `OK` | all seven fields match |
| `MISMATCH` | at least one field differs |
| `NEEDS_REVIEW` | it cannot be decided — unreadable, missing or wrong document |

The seven compared fields, exactly:

```
shipper   consignee   notify_party   port_of_loading
port_of_discharge     container_count     gross_weight_kg
```

**The brief's own warning:** the SI and BL often *label the same field
differently* — `Port of Loading` against `Load Port` — so alignment is by
meaning, not by header text. 65 distinct labels appear across the corpus for
these seven concepts; they are in
[`fields/aliases.py`](../src/sdoc/fields/aliases.py).

Met by [`compare.py`](../src/sdoc/compare.py), with equality decided per field
type in [`normalize/`](../src/sdoc/normalize/).

### When it is a MISMATCH

`has_defect: true` and `defect_fields` listing which of the seven differ.

### When it is NEEDS_REVIEW

`review_reason` set to exactly one of:

| Reason | Meaning |
|---|---|
| `wrong_doc_type` | an attachment is not the document it claims to be |
| `missing_attachment` | one of the two documents is not there |
| `unreadable` | the attachment could not be opened |
| `missing_value` | a compared field is blank or absent |

Precedence between them is decided in `_blocked()` and pinned by test, because
an email can qualify for more than one.

## 3. The output shape

`submission.json`, keyed by `email_id`, matching `sample_submission.json`
**exactly — every email_id present**. Five keys per record, no more and no
fewer:

```json
{
  "email_001": {
    "category": "BL_COMPARISON",
    "status": "MISMATCH",
    "review_reason": null,
    "has_defect": true,
    "defect_fields": ["consignee"]
  }
}
```

Met by `EmailResult.to_submission()`. Checked before the file is ever
submitted by [`validate.py`](../src/sdoc/validate.py), which also enforces the
internal consistency the brief implies but does not spell out: `has_defect`
true if and only if the status is `MISMATCH`, `defect_fields` non-empty on a
`MISMATCH` and empty otherwise, and `review_reason` set if and only if the
status is `NEEDS_REVIEW`.

## 4. How it is scored

```
final = 50%  end-to-end (defects caught all the way through)
      + 30%  Stage-1 macro-F1
      + 20%  Stage-3 defect-F1
```

`NEEDS_REVIEW` handling is reported as a **separate reliability axis**, not
folded into the score.

What each weight implies for the build:

- **50% end-to-end.** A defect only counts if it survives classification,
  extraction *and* comparison. A missed alias upstream loses a defect
  downstream, which is why the alias table and the defect injection harness
  matter more than anything clever in the comparator.
- **30% Stage-1 macro-F1.** *Macro*, so every category weighs the same
  regardless of size. Misfiling one group damages two categories at once —
  its own recall and the precision of wherever the emails land. This is why
  the draft-chaser question is the single highest-value call in the corpus;
  it is settled on evidence in [assumptions.md](assumptions.md).
- **20% Stage-3 defect-F1.** Per-field, so `defect_fields` has to be right,
  not just `has_defect`. Flagging a whole draft for the wrong reason scores
  worse than it looks.
- **The reliability axis.** Escalating is not punished the way a wrong answer
  is, which is the scoring reflecting the real job: a clerk told "the carrier
  sent an invoice, not a bill of lading" can act; one told a wrong consignee
  cannot.

## 5. How the submission reaches them

Two routes, and both are supported:

```bash
python run.py                                    # writes out/submission.json
python run.py --source http://<host>:8080 --submit
```

The organizers either run `score_cli.py submission.json` against the file, or
give out the docker server and take a POST to `/submit`. The HTTP path reads
the sample submission from the server rather than the local copy, because
against a hidden set the local copy describes the wrong emails.

---

## Compliance at a glance

| The brief asks for | Where it happens | What holds it there |
|---|---|---|
| Five categories, every email | `classify.py` | `test_classify.py`, `test_chasers.py` |
| Read the attachments | `documents.py` | `test_documents.py` — `.txt`/`.xlsx`/`.docx`/`.pdf` |
| Align labels by meaning | `fields/aliases.py` | `test_fields.py` — both traps pinned |
| Seven fields compared | `compare.py` | `test_compare.py` |
| Field equality that is not string equality | `normalize/` | `test_normalize.py`, `eval/desk_cases.py` (31/31) |
| `OK` / `MISMATCH` / `NEEDS_REVIEW` | `compare.py` | `test_compare.py` |
| `defect_fields` correct, not just `has_defect` | `compare.py` | `eval/mutation.py` — 602/602, no collateral flags |
| Four escalation reasons, and their precedence | `compare.py::_blocked` | `test_compare.py`, `test_pipeline.py` — 5/5/5/5 |
| Exact submission shape, every email_id | `validate.py` | `test_validate.py`, and the run refuses to finish otherwise |
| Score against ground truth | `eval/score.py` | `test_score.py` — the scorer is itself tested |
| Submit over HTTP | `mailsource.py` | `test_http_source.py` — against a real socket |

347 tests, 602/602 injected defects caught, 31/31 clerk's-eye cases.

## What the brief does not say

Four things it leaves open, each decided deliberately and each recorded with
its reasoning in [assumptions.md](assumptions.md):

1. **91 emails chasing a draft BL** that carry no attachment — operational
   mail, or a comparison that cannot proceed? Settled as `GENERAL` on four
   pieces of corpus evidence; `--chase-as-comparison` flips it.
2. **Whether to compare party addresses** as well as names. Names only.
3. **A confirmed defect alongside an unreadable field** — `MISMATCH`, not
   `NEEDS_REVIEW`, so a caught defect is not buried.
4. **A field present on one document and absent on the other** — not a
   conflict. Only present-and-different counts.

And one thing it does not ask for at all: the brief wants a `submission.json`.
Everything in [`ui/`](../ui) — the queue, the evidence panel, the correction
drafts — is beyond the ask, because a scored file is not a thing a
documentation desk can use.
