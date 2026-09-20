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

The fixing queue arrives in the order to work it, worst first, and Today opens
with a line naming the three bands: *13 stop and fix first — the wrong party
could take the cargo.* Every row carries its band instead of a status tag it
could already infer from the pile it is sitting in, and the panel says which
field earned the band and why. The band is always spelled out, so the colour
repeats the label rather than carrying it.

## Disagreeing with the checker

Beside every comparable row is one control: *these are the same*, or *these
are not the same*. It appears only where an override could mean something —
never on a row nobody could read, and never where both documents say the same
thing, because an override is a rule about a *pair* of values and there is no
pair there.

Recording one changes nothing on the page, and the panel says so. Silencing a
check should not be the side effect of a click, so the correction is kept and
applied later by a person running `tools/apply_overrides.py` with the blast
radius in front of them. "What you have taught it" lists everything recorded,
who recorded it and when, and downloads it as `overrides.json` — the exact
file `sdoc/learned.py` reads. The navigation link for it appears only once
there is something in it.

Corrections live in this browser's `localStorage` and never leave it. That is
right for a prototype and wrong for a desk: shared, a correction one clerk
makes should help the next one, which is a small table behind an endpoint and
the same JSON shape.

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
