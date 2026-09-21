# easyLogistics — Draft Bill of Lading Checking for Shipping Desks

[![Hackathon](https://img.shields.io/badge/Hackathon-Averis%202026-blue)](#)
[![Team](https://img.shields.io/badge/Team-mangkuk-orange)](#)
[![Stack](https://img.shields.io/badge/Stack-Python%20%7C%20Next.js%20%7C%20Supabase-green)](#)
[![Tests](https://img.shields.io/badge/Tests-394%20passing-brightgreen)](docs/validation.md)

> **Team mangkuk — team submission** 🏅

> "The check a shipping clerk does by eye, done the same way every time" —
> comparing every draft bill of lading against the instruction that ordered it,
> ranking what is wrong by what it would cost, and writing the correction email.

### 🌐 [Live site](https://mangkuk-livid.vercel.app) &nbsp;·&nbsp; 🎬 [Video](#) &nbsp;·&nbsp; 📊 [Slide deck](#)

## 👥 Team

**mangkuk** — Averis Hackathon 2026

| Name | Role | Responsibilities |
|------|------|-----------------|
| **Francis** | Full-stack Developer | The checking pipeline, the database, the web app, deployment |
| **Matthew** | Business Research | Market research, the business case, the desk's real workflow |
| **Shen** | Testing | Test coverage, validation, checking the results hold up |
| **Ashley** | Video | The demo video and how the product is presented |

---

## 🌟 Vision

Every container that moves generates a draft bill of lading, and every one has
to be checked against the shipping instruction that ordered it. Today that is
done by eye, hundreds of times a week, under time pressure. easyLogistics does
the comparison in ordinary deterministic code — same documents, same answer,
every rule inspectable — and gives the clerk a short queue, ranked by what each
error would actually cost, with the correction email already written.

### The Problem
- A draft bill of lading arrives for every container and must be checked by hand
- Seven details must match: shipper, consignee, both ports, containers, weight, notify party
- One wrong detail can misroute cargo, release it to the wrong company, or fail customs
- Harmless differences — `21.577,00 KG` vs `21,577 KG` — look identical to a naive checker
- A false alarm costs trust; a missed defect costs a container

### The Solution
| Capability | How easyLogistics Solves It |
|---|---|
| **Deterministic Comparison** | Seven fields compared in plain code — no AI, no variance, every rule inspectable |
| **Normalization** | European decimals, tonnes, port aliases and company suffixes resolved before comparing |
| **Severity Ranking** | Each defect banded by consequence, so the worst is worked first |
| **Escalation, Not Guessing** | Unreadable or blank fields go to a human with the reason stated |
| **Draft Correction Email** | Written and ready, quoting both documents — the clerk sends it themselves |
| **The Email Itself** | The original message and its attachments, one click below the verdict |
| **Learned Corrections** | A desk's corrections are recorded as overrides and replayed on later runs |

---

## 🌍 Impact

- **Fewer wrong bills of lading**: 602 injected defects, 602 caught, zero collateral flags
- **Less wasted chasing**: 31 real-world document quirks, 0 false alarms raised
- **Clerk time returned**: 84.5% of comparison requests decided without a human
- **Auditable by design**: every verdict cites the line and label it came from
- **Works beyond the sample data**: 5 shipments sharing nothing with the pack — 0 wrong verdicts

---

## 🤖 Agentic Ecosystem

The comparison itself uses **no AI**. An LLM stage runs only where the parsers
cannot read a document, and it is disbelieved by default: 62 tests hold it to
that. Default is `off`, so the scored run stays reproducible from the repo alone.

### 📋 Triage Agent
Classifies only what the rule-based classifier abstained on — 59 of 520 emails
in the supplied bundle. Rules decide the remaining 88.7% at high confidence.

### 🔍 Field Resolver Agent
Recovers fields the parsers could not read. It may only *point at* a value
already written in the document — never invent one. Every proposal must return
a verbatim quote, that quote must appear in the document, and the value must
appear inside the quote.

### 🛡️ Grounding Guardrails
A proposal failing any check is discarded and the field stays missing, so the
email escalates exactly as if the agent had never run. Rejected: quotes not in
the document, values not in their quote, implausible values for the field, and
unfilled blanks such as `____MT` or `TBA` that are technically present but say
nothing.

### 🔁 Throttling and Budget
Rate limiting is expected, not exceptional. A per-day quota is detected from the
error body and fails immediately rather than sleeping through six retries, and a
throttled run still produces an identical valid submission.

---

## 🛠️ Tech Stack

| Category | Technology | Purpose |
|---|---|---|
| **Comparison Engine** | Python 3.12 | Deterministic field comparison and normalization |
| **Spreadsheets** | openpyxl | Reading `.xlsx` shipping instructions |
| **Word Documents** | python-docx | Reading `.docx` bills of lading |
| **PDFs** | pypdf | Text extraction from `.pdf` attachments |
| **Testing** | pytest | 394 tests covering every rule, escalation, box type and guardrail |
| **Frontend Framework** | Next.js 15 + React 19 | Server-rendered dashboard |
| **Language** | TypeScript | Type safety across the web app |
| **Database** | Supabase (PostgreSQL) | One row per email, JSONB for nested detail |
| **Row-Level Security** | Supabase RLS | Anon key reads; only the pipeline writes |
| **Hosting** | Vercel | Deploys from `web/`, rendered per request |
| **LLM (recovery)** | Claude, Gemini, or Amazon Bedrock | Documents the parsers cannot read |
| **Config** | python-dotenv | Keys from `.env`, never committed |
| **MCP** | Supabase MCP Server | Database access from the coding agent |

---

## 🚀 Running Locally

### Prerequisites
- Python 3.12+
- Node.js 20+

### The checking pipeline
```bash
pip install -r requirements/base.txt
python run.py
# Reads data/, writes out/submission.json and out/results.json
```

### The website
```bash
python tools/demo_data.py          # scramble identifying values
python tools/supabase_load.py      # load the run into Supabase
npm install --prefix web
npm run dev --prefix web
# Runs at http://localhost:3000
```

Apply the files in `supabase/migrations/` in the Supabase SQL editor first,
in order, or there are no tables to write to.

### Environment Variables

**`.env`** (the pipeline, and the loader)
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_key
GEMINI_API_KEY=your_gemini_key
```

**`web/.env.local`** (the website)
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
```

### Checking the claims
```bash
python -m pytest tests -q          # 394 tests
python eval/rubric.py              # every claim in docs/validation.md, verified
```

---

## 🗺️ Roadmap

- [x] Deterministic comparison of seven fields across `.txt`/`.xlsx`/`.docx`/`.pdf`
- [x] Normalization for decimals, tonnes, port aliases and company suffixes
- [x] Severity banding, worst defect first
- [x] Escalation with a stated reason instead of a guess
- [x] Draft correction email quoting both documents
- [x] LLM recovery stage with grounding guardrails (62 tests)
- [x] Supabase schema, loader, and row-level security
- [x] Next.js dashboard reading the run from Postgres
- [x] Rubric harness checking every published claim against a live run
- [ ] OCR for the five PDFs with no extractable text
- [ ] Learned-corrections page ported to the Next.js app
- [ ] Live mailbox connection instead of a folder
- [ ] Accounts, so a desk shares one queue
- [ ] Sending the correction email directly, once trusted

---

**More detail:** [how accuracy was established](docs/validation.md) ·
[how it runs](docs/usage.md) · [pipeline](docs/pipeline.md) ·
[architecture](docs/architecture.md) · [the site](docs/site.md) ·
[business case](docs/business-case.md) · [open assumptions](docs/assumptions.md)
