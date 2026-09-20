# The site

## The workspace

The unit on screen is a shipment, not an email, and the language is the desk's
rather than the pipeline's — "needs correction", "needs a person", "clear".

Three piles, so a clerk's job becomes working the middle one. Four pickers
narrow the list the way the desk actually thinks — **customer**, **their
country**, **shipping from** and **going to** — and they cascade: choosing
Australia leaves only the customers and destinations that still have
shipments, so no combination ever comes back empty. Free-text search covers
customer, country, address, OC number, port, vessel and cargo. Selecting a
shipment shows its route, cargo, product and carrier, then the seven fields as
the shipping instruction states them beside the draft, with conflicts
highlighted and the source label under every value — so it is visible that the
BL said `To the Order of` where the instruction said `Consignee`.

"Show the lines it read" opens the raw source lines with their line numbers.
That is the glass box, one click deep, out of the way until wanted.

"Draft correction reply" produces a ready email quoting both values per
conflicting field. Nothing is sent — the draft is shown, the clerk sends it.

New users land on a four-step walkthrough: the two documents and the seven
details, the three piles, how to read a mismatch (with a worked example), and
the promise that nothing is ever sent for them. It is skippable, shown once,
and reachable again from the header — and finishing it also settles the
inline explainer on the board, so nobody reads the same thing twice.

Escalations name their reason in plain language and say that the system stopped
rather than guessed. Where a document could not be read there is no extracted
consignee, so the row falls back to the email's own subject instead of
presenting a nameless shipment.

Everything renders from `out/results.json`. There is no backend, no database
and no authentication, which is deliberate: one static file has no deployment
that can fail during a demo.
