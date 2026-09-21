#!/usr/bin/env python3
"""Build one shipment's full correspondence, so the filing can be demonstrated.

    python tools/thread_demo.py
    python run.py --source data/thread-demo --out out/thread \\
                  --sample data/thread-demo/sample_submission.json
    python tools/supabase_load.py --results out/thread/results-demo.json

WHY THIS EXISTS, AND WHAT IT IS NOT

The supplied bundle has no threads. Every reference in it belongs to exactly
one email - 388 OC numbers, 222 bookings, 114 B/L numbers, and not one of them
appears twice - so all 520 shipment files hold a single message and the
grouping never has anything to group. That is a fact about the sample data,
not about the product, and it means the central idea cannot be shown with it.

So this is one container's paperwork from booking to arrival, written rather
than collected: twelve emails, a draft that is wrong twice before it is right,
and the invoice and arrival notice that follow. Every name, port and reference
is invented.

It is kept in its own directory and loaded as its own run for one reason: the
scored submission is 520 emails and must stay 520 emails. Nothing here can
reach it. The ids run from 9001 so that anything constructed is obvious at a
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
CONSIGNEE = "BRAEMAR STATIONERY LIMITED"
WRONG_CONSIGNEE = "BRAEMORE PACKAGING PTE LTD"
POL = "PORT KLANG (WESTPORT), MALAYSIA (MYPKG)"
POD = "FELIXSTOWE, UNITED KINGDOM (GBFXT)"
BOXES = "4 x 40'HC"
WEIGHT = "88,240 KGS"
WRONG_WEIGHT = "86,240 KGS"

DESK = "operations@kiandapulp.example"
CARRIER = "docs@northernline.example"
FINANCE = "billing@northernline.example"


def si() -> str:
    return f"""SHIPPING INSTRUCTION

Shipper/Exporter: {SHIPPER}
To the Order of: {CONSIGNEE}
NOTIFY PARTY: {CONSIGNEE}
Port of Loading (POL): {POL}
PORT OF DISCHARGE: {POD}
No. of Containers: {BOXES}
Kinds of Packages; Description of Goods: WOODFREE PAPER
Gross Wt (kgs): {WEIGHT}
Booking No: {BOOKING}
OC Number: {OC}
Vessel: NORTHERN ADVANCE  Voy: 118W
"""


def bl(consignee: str, weight: str) -> str:
    return f"""BILL OF LADING (DRAFT)

B/L Number: {BL}
SHIPPER: {SHIPPER}
Consignee (Non-Negotiable): {consignee}
Notify: {CONSIGNEE}
Load Port: {POL}
Port of Discharge: {POD}
No. of Containers: {BOXES}
GROSS WEIGHT: {weight}
Booking: {BOOKING}
Ocean Vessel: NORTHERN ADVANCE  Voyage: 118W
"""


def note(eid, sender, subject, body, si_text=None, bl_text=None):
    e = {"email_id": eid, "from": sender, "subject": subject, "body": body,
         "attachments": []}
    if si_text:
        e["attachments"].append(f"attachments/{eid}_SI.txt")
        e["_si"] = si_text
    if bl_text:
        e["attachments"].append(f"attachments/{eid}_BL.txt")
        e["_bl"] = bl_text
    return e


# One container, booking to arrival. Three drafts: the first has two things
# wrong, the second fixes one of them, the third is right. That shape matters -
# a demo where the first correction lands says nothing about what a desk
# actually spends its week on.
THREAD = [
    note("email_9001", CARRIER,
         f"BOOKING CONFIRMED _ {BOOKING} _ NORTHERN ADVANCE 118W",
         f"""Dear Sir or Madam,

Booking {BOOKING} is confirmed on NORTHERN ADVANCE voyage 118W, Port Klang to
Felixstowe. Cut-off is Thursday 14:00. Please send your shipping instruction.

Regards,
Documentation Desk
Northern Line
"""),

    note("email_9002", DESK,
         f"SHIPPING INSTRUCTION _ {OC} _ {BOOKING}",
         f"""Hi,

Shipping instruction attached for OC {OC}, booking {BOOKING}. Four 40' high
cubes of woodfree paper to Felixstowe.

Please send the draft B/L for checking.

Best Regards,
Operations
Kianda Pulp & Paper Sdn Bhd
""",
         si_text=si()),

    note("email_9003", CARRIER,
         f"DRAFT BL FOR CHECKING _ {OC} _ FELIXSTOWE_UK _ {BOOKING}",
         f"""Dear Sir or Madam,

Please find the draft bill of lading for OC {OC}. Kindly check and confirm.

Regards,
Documentation Desk
Northern Line
""",
         si_text=si(), bl_text=bl(WRONG_CONSIGNEE, WRONG_WEIGHT)),

    note("email_9004", CARRIER,
         f"RE: DRAFT BL FOR CHECKING _ {OC}",
         f"""Dear Sir or Madam,

Thank you for your message on booking {BOOKING}. We are checking the consignee
and the gross weight against our records and will revert.

Regards,
Documentation Desk
Northern Line
"""),

    note("email_9005", CARRIER,
         f"AMENDED DRAFT BL _ {OC} _ {BOOKING}",
         f"""Dear Sir or Madam,

Amended draft attached for OC {OC}. The consignee has been corrected to
{CONSIGNEE}.

Regards,
Documentation Desk
Northern Line
""",
         si_text=si(), bl_text=bl(CONSIGNEE, WRONG_WEIGHT)),

    note("email_9006", DESK,
         f"RE: AMENDED DRAFT BL _ {OC} _ gross weight still differs",
         f"""Hi,

Thank you. The consignee is correct now. The gross weight on the draft still
reads {WRONG_WEIGHT} where our instruction says {WEIGHT}.

Could you confirm which is right? If the instruction has been amended since we
sent it, please point us to the amendment.

Best Regards,
Operations
Kianda Pulp & Paper Sdn Bhd
"""),

    note("email_9007", CARRIER,
         f"RE: {OC} _ weight confirmed from VGM",
         f"""Dear Sir or Madam,

Checked against the VGM for booking {BOOKING}. You are correct - {WEIGHT} is
the figure. The draft carried a transposition. Amended copy to follow.

Regards,
Documentation Desk
Northern Line
"""),

    note("email_9008", CARRIER,
         f"AMENDED DRAFT BL (2) _ {OC} _ {BOOKING}",
         f"""Dear Sir or Madam,

Second amended draft for OC {OC}, with the gross weight corrected to {WEIGHT}.

Kindly confirm so we may release the originals.

Regards,
Documentation Desk
Northern Line
""",
         si_text=si(), bl_text=bl(CONSIGNEE, WEIGHT)),

    note("email_9009", DESK,
         f"RE: AMENDED DRAFT BL (2) _ {OC} _ approved",
         f"""Hi,

Checked and approved. All seven details match our instruction. Please release
the originals for booking {BOOKING}.

Best Regards,
Operations
Kianda Pulp & Paper Sdn Bhd
"""),

    note("email_9010", CARRIER,
         f"B/L {BL} _ originals released",
         f"""Dear Sir or Madam,

The originals for B/L {BL} (booking {BOOKING}) have been released and are
available for collection at our Port Klang counter.

Regards,
Documentation Desk
Northern Line
"""),

    note("email_9011", FINANCE,
         f"INVOICE 5250099 _ {BOOKING} _ ocean freight",
         f"""Dear Sir or Madam,

Please find our invoice 5250099 for ocean freight on booking {BOOKING},
NORTHERN ADVANCE 118W. Payment terms 30 days.

Regards,
Billing
Northern Line
"""),

    note("email_9012", CARRIER,
         f"ARRIVAL NOTICE _ {BOOKING} _ FELIXSTOWE",
         f"""Dear Sir or Madam,

NORTHERN ADVANCE voyage 118W is scheduled to berth at Felixstowe on the 19th.
Four containers under booking {BOOKING} will be available for collection after
customs clearance.

Regards,
Documentation Desk
Northern Line
"""),
]


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "inbox").mkdir(parents=True)
    (OUT / "attachments").mkdir()

    for e in THREAD:
        si_text, bl_text = e.pop("_si", None), e.pop("_bl", None)
        if si_text:
            (OUT / "attachments" / f"{e['email_id']}_SI.txt").write_text(
                si_text, encoding="utf-8")
        if bl_text:
            (OUT / "attachments" / f"{e['email_id']}_BL.txt").write_text(
                bl_text, encoding="utf-8")
        (OUT / "inbox" / f"{e['email_id']}.json").write_text(
            json.dumps(e, indent=1), encoding="utf-8")

    (OUT / "sample_submission.json").write_text(
        json.dumps({e["email_id"]: {
            "category": "GENERAL", "status": "OK", "review_reason": None,
            "defect_fields": [], "has_defect": False,
        } for e in THREAD}, indent=1), encoding="utf-8")

    (OUT / "README.md").write_text(
        "# One shipment, twelve emails\n\n"
        "A constructed correspondence: booking confirmed, instruction sent, a "
        "draft bill of lading with two things wrong, one correction that fixes "
        "only one of them, a second that fixes the other, approval, release, "
        "invoice and arrival notice.\n\n"
        "Every name, port and reference is invented. The supplied bundle "
        "contains no threads at all - each of its 520 emails is the only one "
        "that mentions its reference - so the filing cannot be demonstrated "
        "with it. This is not sample data and is never part of the scored run, "
        "which is 520 emails and stays 520 emails.\n\n"
        "All twelve file together on the booking. The three drafts also share "
        "a B/L number, which is the reference a carrier quotes when replying "
        "about a document.\n",
        encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)}: {len(THREAD)} emails, "
          f"{len(list((OUT / 'attachments').iterdir()))} attachments")
    print(f"  one shipment: OC {OC}, booking {BOOKING}, B/L {BL}")
    print("\nnext:")
    print("  python run.py --source data/thread-demo --out out/thread \\")
    print("                --sample data/thread-demo/sample_submission.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
