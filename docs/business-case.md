# Business case and roadmap

## Business viability

**What it replaces.** A clerk opening two attachments and eye-comparing seven
fields. Assuming five minutes per check — an estimate to confirm with the
operations team, not a measured figure — the 129 checks in this batch are about
**11 hours** of desk time.

The system decides 109 of them outright and escalates 20 with the reason
already stated. At roughly two minutes to action a pre-diagnosed escalation,
that is about **40 minutes of human time**, against 11 hours. The saving is
in the same order as the work itself, and it scales with volume rather than
headcount.

**Where the money actually is.** Not the minutes — the 46 defective drafts
caught before release. A wrong consignee or port on a released BL means an
amendment fee, a delayed release, and in the worst case cargo moving against a
document naming the wrong party. Catching those is worth more than the clerical
time, and the system caught them at a rate of 42.2% of decided checks.

**Why an ops team would actually use it.** The unit on screen is a shipment,
not an email. The vocabulary is "needs correction", not `MISMATCH`. Every flag
shows both values and the labels they came from, so the correction email
writes itself and the clerk stays accountable for sending it. Nothing is
auto-sent.

**Adoption risk, handled.** The system never guesses. 15.5% of checks come back
as "a person needs to look at this, and here is exactly why". A tool that
silently guessed on those would be abandoned the first time it was wrong on
something expensive.

**Deployment shape.** Graph change notifications into API Gateway and Lambda,
S3 for raw documents, Step Functions per email so a throttle retries one stage
rather than the batch, Bedrock over a VPC endpoint so document text never
leaves the tenant, DynamoDB keyed on OC number, static front end on S3 and
CloudFront, corrections written back as Outlook drafts rather than sent. Full
diagram, security posture and costs in [docs/architecture.md](architecture.md).

**What it is not.** Not a BL generator — the carrier issues the BL. Not an
auto-sender. Not a replacement for the documentation team; it is an exception
desk that turns 129 document checks into 20 judgement calls and 46
ready-to-send corrections.

## Roadmap

### Completing the build

PDF extraction via Textract, which recovers the 15 unreadable checks. An LLM
adjudicator on Bedrock for the 11.3% classifier residue and for extraction on
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
