"""One vocabulary for the whole system.

The scorer needs `BL_COMPARISON`; a shipping clerk needs "document check".
Both are kept here, together, so the screen, the reports and the documentation
cannot drift into three different words for the same thing.

The keys are the organizers' values and must not be renamed. Only the
right-hand side is ours.
"""
from __future__ import annotations

CATEGORY_LABELS: dict[str, str] = {
    "BL_COMPARISON": "Document check",
    "SI_REQUEST": "Instruction request",
    "INVOICE_QUERY": "Invoice question",
    "GENERAL": "General mail",
    "SPAM": "Spam",
}

CATEGORY_BLURBS: dict[str, str] = {
    "BL_COMPARISON": "a draft bill of lading to check against its instruction",
    "SI_REQUEST": "preparing, requesting or submitting a shipping instruction",
    "INVOICE_QUERY": "an invoice, freight charge or billing question",
    "GENERAL": "operational traffic - vessel updates, reports, reminders",
    "SPAM": "unsolicited mail, phishing and scams",
}

STATUS_LABELS: dict[str, str] = {
    "MISMATCH": "Needs fixing",
    "NEEDS_REVIEW": "Needs you to look",
    "OK": "Fine",
    # Not one of the organizers' statuses, and never written to a submission.
    # The pipeline stores OK on every email it was not asked to check, so the
    # screen needs a word for "no check was run here" that is not "Fine".
    "UNCHECKED": "No check",
}

# Short machine-ish tone names, used for colour and CSS classes.
STATUS_TONES: dict[str, str] = {
    "MISMATCH": "fix",
    "NEEDS_REVIEW": "look",
    "OK": "fine",
    "UNCHECKED": "idle",
}

REASON_LABELS: dict[str, str] = {
    "wrong_doc_type": "The carrier sent the wrong kind of document",
    "missing_attachment": "One of the two documents is missing",
    "unreadable": "The attachment could not be opened",
    "missing_value": "A detail is blank on the instruction",
}

# The severity bands from sdoc/severity.py, said the way a desk would say
# them. The ranking lives there; only the wording lives here.
BAND_LABELS: dict[str, str] = {
    "critical": "Stop and fix first",
    "serious": "Fix before release",
    "routine": "Fix when you get to it",
}

BAND_BLURBS: dict[str, str] = {
    "critical": "the wrong party could take the cargo",
    "serious": "cargo could be misrouted, or the declaration refused",
    "routine": "an amendment, a delay and a corrected invoice",
}

FIELD_LABELS: dict[str, str] = {
    "shipper": "Shipper",
    "consignee": "Consignee",
    "notify_party": "Notify party",
    "port_of_loading": "Loading port",
    "port_of_discharge": "Discharge port",
    "container_count": "Containers",
    "gross_weight_kg": "Gross weight",
}


def as_payload() -> dict:
    """The whole vocabulary, for embedding in results so the UI reuses it."""
    return {
        "category": CATEGORY_LABELS,
        "category_blurb": CATEGORY_BLURBS,
        "status": STATUS_LABELS,
        "tone": STATUS_TONES,
        "reason": REASON_LABELS,
        "field": FIELD_LABELS,
        "band": BAND_LABELS,
        "band_blurb": BAND_BLURBS,
    }
