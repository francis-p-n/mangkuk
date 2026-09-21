#!/usr/bin/env python3
"""Build a constructed shipment thread, so the filing can be demonstrated.

    python tools/thread_demo.py              # writes data/thread-demo/
    python run.py --source data/thread-demo --out out/thread
    python tools/supabase_load.py --results out/thread/results-demo.json

WHY THIS EXISTS, AND WHAT IT IS NOT

The supplied bundle has no threads. Every reference in it belongs to exactly
one email - 388 OC numbers across 388 emails, 222 bookings across 222, ten B/L
numbers across ten - so all 520 shipment files hold a single message and the
grouping never has anything to group. That is a fact about the sample data,
not about the product, but it means the central idea cannot be shown using it.

So these four emails are written, not collected. They are the ordinary life of
one correction: the carrier sends a draft, the desk finds the consignee wrong,
the carrier sends it again fixed, and the shipment closes. Every name, port and
reference in them is invented.

It is kept in its own directory and loaded as its own run for one reason: the
scored submission is 520 emails and must stay 520 emails. Nothing here can
reach it.

The ids run from email_9001 so that anything constructed is obvious at a
glance against a corpus numbered 001 to 520 - and so the bundle loader, which
globs email_*.json, can see them at all.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "thread-demo"

OC = "7QTX-40118"
BOOKING = "MEDUTH550281"
BL = "MEDUTH550281X"

SHIPPER = "KIANDA PULP & PAPER SDN BHD"
RIGHT_CONSIGNEE = "BRAEMAR STATIONERY LIMITED"
WRONG_CONSIGNEE = "BRAEMORE PACKAGING PTE LTD"
POL = "PORT KLANG (WESTPORT), MALAYSIA (MYPKG)"
POD = "FELIXSTOWE, UNITED KINGDOM (GBFXT)"
BOXES = "4 x 40'HC"
WEIGHT = "88,240 KGS"

SI = f"""SHIPPING INSTRUCTION

Shipper/Exporter: {SHIPPER}
To the Order of: {RIGHT_CONSIGNEE}
NOTIFY PARTY: {RIGHT_CONSIGNEE}
Port of Loading (POL): {POL}
PORT OF DISCHARGE: {POD}
No. of Containers: {BOXES}
Kinds of Packages; Description of Goods: WOODFREE PAPER
Gross Wt (kgs): {WEIGHT}
Booking No: {BOOKING}
OC Number: {OC}
Vessel: NORTHERN ADVANCE  Voy: 118W
"""


def bl(consignee: str) -> str:
    return f"""BILL OF LADING (DRAFT)

B/L Number: {BL}
SHIPPER: {SHIPPER}
Consignee (Non-Negotiable): {consignee}
Notify: {RIGHT_CONSIGNEE}
Load Port: {POL}
Port of Discharge: {POD}
No. of Containers: {BOXES}
GROSS WEIGHT: {WEIGHT}
Booking: {BOOKING}
Ocean Vessel: NORTHERN ADVANCE  Voyage: 118W
"""


# The thread. Each email names the shipment by at least one of its three
# references, which is what files them together - the last one quotes only the
# B/L number, which is how a carrier usually replies about a document and the
# reason that alias is an edge at all.
THREAD = [
    {
        "email_id": "email_9001",
        "from": "operations@kiandapulp.example",
        "subject": f"TO CONFIRM DOCS _ {OC} _ FELIXSTOWE_UK _ "
                   f"{RIGHT_CONSIGNEE} _ {BOOKING}",
        "body": f"""Hi,

Attached are the SI and draft BL for OC {OC} (WOODFREE PAPER). Please check
the details and confirm.

Best Regards,
Operations
Kianda Pulp & Paper Sdn Bhd
""",
        "attachments": ["attachments/email_9001_SI.txt",
                        "attachments/email_9001_BL.txt"],
        "_si": SI,
        "_bl": bl(WRONG_CONSIGNEE),
    },
    {
        "email_id": "email_9002",
        "from": "docs@northernline.example",
        "subject": f"RE: TO CONFIRM DOCS _ {OC} _ FELIXSTOWE_UK",
        "body": f"""Dear Sir or Madam,

Thank you for your message regarding booking {BOOKING}. We are checking the
consignee against our records and will revert with an amended draft shortly.

Regards,
Documentation Desk
Northern Line
""",
        "attachments": [],
    },
    {
        "email_id": "email_9003",
        "from": "docs@northernline.example",
        "subject": f"AMENDED DRAFT BL _ {OC} _ {BOOKING}",
        "body": f"""Dear Sir or Madam,

Please find the amended draft bill of lading for OC {OC}. The consignee has
been corrected to {RIGHT_CONSIGNEE} as per your shipping instruction.

Kindly confirm so we may release the original.

Regards,
Documentation Desk
Northern Line
""",
        "attachments": ["attachments/email_9003_SI.txt",
                        "attachments/email_9003_BL.txt"],
        "_si": SI,
        "_bl": bl(RIGHT_CONSIGNEE),
    },
    {
        "email_id": "email_9004",
        "from": "docs@northernline.example",
        "subject": f"B/L {BL} - originals released",
        "body": f"""Dear Sir or Madam,

The originals for B/L {BL} (booking {BOOKING}) have been released and are
available for collection at our Port Klang counter.

Regards,
Documentation Desk
Northern Line
""",
        # No OC. It files with the rest on the booking, and carries the B/L
        # number that emails 9001 and 9003 also carry on their drafts - the
        # alias that joins a carrier's document reply to the shipment.
        "attachments": [],
    },
]


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "inbox").mkdir(parents=True)
    (OUT / "attachments").mkdir()

    for e in THREAD:
        si, bl_text = e.pop("_si", None), e.pop("_bl", None)
        if si:
            (OUT / "attachments" / f"{e['email_id']}_SI.txt").write_text(
                si, encoding="utf-8")
        if bl_text:
            (OUT / "attachments" / f"{e['email_id']}_BL.txt").write_text(
                bl_text, encoding="utf-8")
        (OUT / "inbox" / f"{e['email_id']}.json").write_text(
            json.dumps(e, indent=1), encoding="utf-8")

    # The bundle loader expects one; a thread has no scoring to do.
    (OUT / "sample_submission.json").write_text(
        json.dumps({e["email_id"]: {
            "category": "GENERAL", "status": "OK", "review_reason": None,
            "defect_fields": [], "has_defect": False,
        } for e in THREAD}, indent=1), encoding="utf-8")

    (OUT / "README.md").write_text(
        "# A constructed thread\n\n"
        "Four emails written to show one shipment being corrected: a draft "
        "with the wrong consignee, the carrier acknowledging, an amended "
        "draft that matches, and the release notice.\n\n"
        "Every name, port and reference here is invented. The supplied bundle "
        "contains no threads at all - each of its 520 emails is the only one "
        "that mentions its reference - so the filing cannot be demonstrated "
        "with it. This is not sample data and is never part of the scored "
        "run, which is 520 emails and stays 520 emails.\n\n"
        "The last email quotes only the B/L number. It files itself with the "
        "other three through that alias alone, which is how a carrier usually "
        "replies about a document.\n",
        encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)}: {len(THREAD)} emails, "
          f"{len(list((OUT / 'attachments').iterdir()))} attachments")
    print(f"  references: OC {OC}, booking {BOOKING}, B/L {BL}")
    print("\nnext:")
    print("  python run.py --source data/thread-demo --out out/thread")
    print("  python tools/supabase_load.py --results out/thread/results-demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
