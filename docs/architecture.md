# Production architecture

Two clouds appear in this design, and only one of them is a choice.

**AWS** runs everything the system does: storage, compute, the model, the
database, the front end. That follows Averis already being on AWS.

**Microsoft** is where the mail lives. The desk runs on Outlook, so ingestion
goes through the Microsoft Graph API. That needs exactly one Microsoft-side
artefact — an **Entra ID app registration** granting `Mail.Read` on the shared
documentation mailbox. No Azure compute, no Azure storage, no Azure Functions.
Object storage is **S3**; "bucket" is the S3 word, and Azure's equivalent
(Blob Storage containers) is not used here at all.

So: one Entra app registration, and everything else on AWS.

## The path a shipment takes

```
Outlook mailbox
   | Graph change notification (webhook)
   v
API Gateway  ->  Lambda: ingest
                   | validates the Graph subscription token
                   | writes raw email + attachments
                   v
                 S3  (raw/)              <- versioned, SSE-KMS, immutable
                   |
                   v
             Step Functions: one execution per email
                   |
      +------------+------------+------------+
      |            |            |            |
   classify     extract      compare      escalate
   (Lambda)    (Lambda +    (Lambda,     (Lambda ->
               Textract)    no model)     Graph draft)
      |            |            |            |
      +------------+------------+------------+
                   |
                   v
              DynamoDB  (shipments, verdicts, evidence)
                   |
                   v
          S3 (results/) -> CloudFront -> the workspace
```

### Ingestion

Graph change notifications push on arrival rather than being polled, so the
clerk sees a verdict within seconds of the mail landing. Subscriptions expire
and must be renewed; an EventBridge rule on a schedule handles that, and it is
the single most common thing to get wrong in a Graph integration.

The ingest Lambda does no parsing. It validates the notification, pulls the
message and attachments through Graph, writes them to `s3://…/raw/`, and starts
one Step Functions execution. Keeping it dumb means a parser bug never costs
you the source document.

### Why Step Functions rather than chained Lambdas

The stages are already separated by JSON contracts, which is exactly what a
state machine wants. What it buys:

- **Retries and backoff per stage.** A Bedrock throttle retries the model call,
  not the whole email.
- **A visible execution graph.** During a demo you can point at a live run and
  show which stage a shipment is in. Chained Lambdas give you log grepping.
- **A catch branch per stage** that routes to escalation with the failure
  reason attached — the same `NEEDS_REVIEW` path a blank field takes, so
  infrastructure failure and document failure are handled identically.
- **Per-execution history**, which is the audit trail an outsourcing provider
  will be asked for.

SQS still belongs between ingestion and the state machine, with a dead-letter
queue, so a burst of 500 emails queues rather than throttling.

### Where the model runs

**Bedrock**, reached over a **VPC interface endpoint**, so document text never
traverses the public internet and never leaves the tenant. This is the answer
to the question an outsourcing provider's security review will ask first, and
it is the reason not to call a third-party API directly.

**Textract** handles the scanned PDFs — the five in the bundle that extract to
nothing today. Asynchronous `StartDocumentTextDetection`, with the job callback
returning into the state machine.

Both are reached only for what the deterministic stages could not do. On the
sample corpus that is 3 fields across 2 documents, so the model cost is close
to noise; Textract is the more significant line item, and only for image PDFs.

### State

**DynamoDB**, single table, partition key `SHIPMENT#<oc_number>`:

| Item | Sort key | Holds |
|---|---|---|
| Shipment | `META` | consignee, route, cargo, product, carrier |
| Email | `EMAIL#<id>` | category, sender, received time |
| Verdict | `VERDICT#<email_id>` | status, defect fields, evidence quotes |

Querying one partition returns the whole shipment thread, which is exactly
what the workspace's detail pane renders. Unassigned emails — no OC number
found — go to a separate partition rather than being guessed into a shipment.

**S3** keeps the raw documents and the generated `results.json`. DynamoDB holds
what is queried; S3 holds what is read whole.

### The front end

The workspace is already a single static file. It goes to S3 behind
**CloudFront**, with **Cognito** in front when this stops being a demo. No
server, no container, nothing to patch.

### Outbound

Corrections are written back as **Outlook drafts via Graph**, into the clerk's
own mailbox — not sent by SES. Two reasons: it keeps the human as the sender,
which is the whole adoption argument; and it means the reply threads correctly
in the conversation the carrier is already reading.

### Security posture

KMS on every bucket and table. VPC endpoints for S3, DynamoDB and Bedrock, so
no traffic leaves the VPC. IAM per-Lambda, least privilege — the classify
Lambda cannot read the raw bucket. Graph credentials in Secrets Manager with
rotation. CloudTrail on, and the seven-field evidence record is itself an audit
artefact: for any verdict you can show which line of which document produced
it.

## What actually runs this weekend

The hackathon build runs the same stage code locally against the bundle, with
Bedrock as the only cloud call. The diagram above is the production shape, and
it is honest to present it that way: the stage boundaries are already JSON
contracts, so each box is the existing module behind a Lambda handler rather
than a rewrite.

Worth saying out loud in the deck — a judge who has built on AWS will trust
"here is what runs, here is what it becomes, and here is why the seam is
already in the right place" far more than a half-wired queue.

## Rough running cost

Per 1,000 emails, order of magnitude only:

- Lambda, Step Functions, SQS, API Gateway: cents
- S3 and DynamoDB at this volume: cents
- Bedrock: only the residue the parsers miss — on the sample corpus that is
  about 2% of documents
- Textract: the real variable, and only for image-only PDFs

The dominant cost is Textract, not the model. That is worth knowing before
promising OCR on everything.

## On "training the model"

There is nothing here worth fine-tuning, and doing it would make the system
worse.

The comparison stage is deterministic code, and it already catches 602 of 602
injected defects with no collateral false flags. A model cannot beat that, and
substituting one would trade an explainable rule for an unexplainable weight.

For the extraction stage, fine-tuning needs labelled examples, and the bundle
ships no ground truth. 129 document pairs from a single generator would teach
a model that generator's quirks — exactly the quirks that will not appear in
the organizers' hidden test set.

The documents *are* valuable, just not as training data:

- the 66 distinct field labels became the alias table in `fields/aliases.py`
- the label variants became unit tests, including the traps
- the clean pairs became mutation hosts — 63 of them, 602 injected defects
- the real values became `eval/desk_cases.py`, which is what found the
  European decimal, tonne, ampersand and port-alias gaps

That is the same information a fine-tune would extract, in a form that is
inspectable, testable, and free to run.
