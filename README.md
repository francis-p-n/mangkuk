# easyLogistics

**Team mangkuk — team submission**

[Watch the video](#) · [See the slide deck](#)

---

## 1. The problem, and what we built

Every container that moves gets a draft bill of lading from the carrier.
Each one must be checked by eye against the instruction the exporter sent:
shipper, consignee, ports, weights, box counts. A clerk does this hundreds
of times a week under time pressure. One wrong detail can send cargo to the
wrong country, hand it to the wrong company, or get it refused at the border.

We built the check. It reads the email, finds both documents, compares them
detail by detail, and says plainly what is wrong and how badly it matters.
The clerk gets a short queue and a ready-written email instead of a full inbox.

## 2. What it does

- Reads every email and finds the two documents automatically
- Compares seven key details between the instruction and the draft
- Ignores harmless differences in spelling, spacing and number formats
- Flags only real problems, so nobody chases a false alarm
- Ranks each problem by how much damage it would cause
- Writes the correction email, ready for the clerk to send
- Never guesses — anything unreadable goes to a person
- Remembers corrections the desk makes and applies them later
- Shows its working, so every verdict can be checked
- Runs the same way twice, so results can be trusted

## 3. Tech stack

| Part | What we used |
|---|---|
| Checking engine | Python 3.12 |
| Reading documents | openpyxl, python-docx, pypdf |
| Database | Supabase (Postgres) |
| Website | Next.js, React, TypeScript |
| Hosting | Vercel |
| AI recovery stage | Claude, Gemini, or Amazon Bedrock |

The comparison itself uses no AI. It is ordinary code, so the same documents
always give the same answer, and every rule can be inspected. AI is used only
for documents the readers cannot open, and even then it may only point at a
value already written in the document — never invent one.

## 4. What comes next

- Reading scanned PDFs that have no text in them
- Connecting straight to a live mailbox instead of a folder
- Accounts, so a team can share one queue
- Sending the correction email directly, once trusted
- Handling more document types beyond bills of lading
- Learning across the whole desk, not one person

---

**More detail:** [how accuracy was established](docs/validation.md) ·
[how it runs](docs/pipeline.md) · [architecture](docs/architecture.md) ·
[the site](docs/site.md) · [business case](docs/business-case.md) ·
[open assumptions](docs/assumptions.md) · [how to run it](docs/usage.md)
