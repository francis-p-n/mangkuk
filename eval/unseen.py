#!/usr/bin/env python3
"""Does it work on paper the bundle never contained?

    python eval/unseen.py
    python eval/unseen.py --verbose      # every field of every case

Every other harness in here measures the checker against the supplied corpus.
This one measures it against documents written to have nothing to do with the
corpus: different trades, different lanes, different companies, different
numeric conventions, and label wording the pack does not use.

The question is not "does it get everything right" - it will not, and the
interesting part is *how* it fails. Two numbers matter, and they are not the
same number:

  READ      the vocabulary it recognises on unfamiliar paper. A miss here
            costs a comparison and escalates the email. Inconvenient.

  WRONG     a field it read and then judged incorrectly - a defect invented,
            or a real one waved through. Dangerous, because the desk acts on
            it, and the whole posture of this project is that it would rather
            say "I could not read this" than guess.

A checker fitted to the corpus would score badly on READ and, worse, would
start inventing comparisons out of half-parsed text. One that has learned the
shipping framework degrades into honest escalation. So READ is allowed to be
imperfect. WRONG is not allowed to be anything but zero.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sdoc.compare import compare_documents          # noqa: E402
from sdoc.documents import Document, DocType        # noqa: E402


@dataclass
class Case:
    name: str
    why: str                       # what about this one is unfamiliar
    si: str
    bl: str
    defects: set[str]              # planted, and they must be found
    same: set[str] = dc_field(default_factory=set)   # rewritten, must NOT flag


def doc(text: str, role: str, kind: DocType) -> Document:
    return Document(path=f"unseen_{role}.txt", role=role, fmt=".txt",
                    text=text, doc_type=kind, ok=True)


CASES: list[Case] = [

    Case(
        name="Brazilian coffee, Santos to Hamburg",
        why="labels the pack never uses: Exporter, Receiver, From/To Port, "
            "Total Gross, Units; weight in tonnes with a decimal comma",
        si="""SHIPPING INSTRUCTION - REF BRC-88213

Exporter: CAFEEIRA SANTOS EXPORTADORA LTDA
Receiver: NORDKAFFEE HANDELS GMBH
Also Notify: NORDKAFFEE HANDELS GMBH
From Port: SANTOS, BRAZIL (BRSSZ)
To Port: HAMBURG, GERMANY (DEHAM)
Units: 12 x 20'DV
Total Gross: 268,4 MT
Commodity: GREEN COFFEE BEANS, ARABICA
""",
        bl="""BILL OF LADING  No. NMJ4410221

SHIPPER: CAFEEIRA SANTOS EXPORTADORA LTDA
CONSIGNEE: HANSEATIC BEAN IMPORTS AG
NOTIFY: NORDKAFFEE HANDELS GMBH
Port of Loading: SANTOS, BRAZIL (BRSSZ)
Port of Discharge: HAMBURG, GERMANY (DEHAP)
No. of Pkgs: 12 x 20'GP
Gross Weight: 268,400 KGS
""",
        defects={"consignee", "port_of_discharge"},
        same={"container_count", "gross_weight_kg", "shipper", "notify_party"},
    ),

    Case(
        name="Korean steel coil, Busan to Houston",
        why="conventional labels, unfamiliar lane and commodity; the box "
            "type written the long way instead of as a code",
        si="""SHIPPING INSTRUCTION

Shipper: DAEHAN COIL & PLATE CO., LTD
Consignee: GULF METALS PROCESSING INC
Notify Party: GULF METALS PROCESSING INC
Port of Loading: BUSAN, KOREA (KRPUS)
Port of Discharge: HOUSTON, TX, USA (USHOU)
Container: 8 x 40'HC
Gross Weight: 214,500 KGS
""",
        bl="""BILL OF LADING

Shipper: DAEHAN COIL & PLATE CO., LTD
Consignee: GULF METALS PROCESSING INC
Notify Party: GULF METALS PROCESSING INC
Port of Loading: BUSAN, KOREA (KRPUS)
Port of Discharge: HOUSTON, TX, USA (USHOU)
Container: 8 x 40'HIGH CUBE
Gross Weight: 214,500 KGS
""",
        defects=set(),
        same={"container_count", "gross_weight_kg"},
    ),

    Case(
        name="Dutch flower bulbs, Rotterdam to Santos",
        why="reversed lane, European company forms, and a consignee written "
            "with a legal suffix the pack does not contain",
        si="""SHIPPING INSTRUCTION

Shipper: VAN DER HEIDEN BLOEMBOLLEN B.V.
Consignee: FLORES DO SUL COMERCIO LTDA
Notify Party: FLORES DO SUL COMERCIO LTDA
Port of Loading: ROTTERDAM, NETHERLANDS (NLRTM)
Port of Discharge: SANTOS, BRAZIL (BRSSZ)
Container: 3 x 40'RF
Gross Weight: 41.250,00 KG
""",
        bl="""BILL OF LADING

Shipper: Van der Heiden Bloembollen BV
Consignee: FLORES DO SUL COMERCIO LTDA
Notify Party: FLORES DO SUL COMERCIO LTDA
Port of Loading: ROTTERDAM, NETHERLANDS (NLRTM)
Port of Discharge: SANTOS, BRAZIL (BRSSZ)
Container: 3 x 40'RF
Gross Weight: 41,250 KG
""",
        # 'B.V.' against 'BV', and a European decimal against a thousands
        # separator for the same mass. Both are the same thing said twice.
        defects=set(),
        same={"shipper", "gross_weight_kg"},
    ),

    Case(
        name="Indian textiles, Nhava Sheva to Felixstowe",
        why="a planted weight error of exactly one tonne, which a checker "
            "that rounds or ignores small differences would miss",
        si="""SHIPPING INSTRUCTION

Shipper: SURAT WEAVING MILLS PVT LTD
Consignee: ALBION FABRICS LIMITED
Notify Party: ALBION FABRICS LIMITED
Port of Loading: NHAVA SHEVA, INDIA (INNSA)
Port of Discharge: FELIXSTOWE, UNITED KINGDOM (GBFXT)
Container: 5 x 40'GP
Gross Weight: 62,000 KGS
""",
        bl="""BILL OF LADING

Shipper: SURAT WEAVING MILLS PVT LTD
Consignee: ALBION FABRICS LIMITED
Notify Party: ALBION FABRICS LIMITED
Port of Loading: NHAVA SHEVA, INDIA (INNSA)
Port of Discharge: FELIXSTOWE, UNITED KINGDOM (GBFXT)
Container: 5 x 40'GP
Gross Weight: 63,000 KGS
""",
        defects={"gross_weight_kg"},
        same={"shipper", "consignee", "port_of_loading", "container_count"},
    ),

    Case(
        name="Chilean wine, Valparaiso to Yokohama",
        why="the subtle one: the discharge city is right and only the "
            "UN/LOCODE is wrong, on a lane the pack does not carry",
        si="""SHIPPING INSTRUCTION

Shipper: VINA COSTA AZUL S.A.
Consignee: TOKYO FINE WINES KK
Notify Party: TOKYO FINE WINES KK
Port of Loading: VALPARAISO, CHILE (CLVAP)
Port of Discharge: YOKOHAMA, JAPAN (JPYOK)
Container: 2 x 20'RF
Gross Weight: 38,400 KGS
""",
        bl="""BILL OF LADING

Shipper: VINA COSTA AZUL S.A.
Consignee: TOKYO FINE WINES KK
Notify Party: TOKYO FINE WINES KK
Port of Loading: VALPARAISO, CHILE (CLVAP)
Port of Discharge: YOKOHAMA, JAPAN (JPYOH)
Container: 2 x 20'RF
Gross Weight: 38,400 KGS
""",
        defects={"port_of_discharge"},
        same={"port_of_loading", "consignee"},
    ),
]


def run(case: Case):
    v = compare_documents(
        doc(case.si, "SI", DocType.SHIPPING_INSTRUCTION),
        doc(case.bl, "BL", DocType.BILL_OF_LADING),
    )
    by = {c.field: c for c in v.comparisons}

    read = {f for f, c in by.items() if c.agree is not None}
    found = {f for f, c in by.items() if c.agree is False}

    # Only fields it actually read can be judged. A field it could not read is
    # a coverage miss, counted separately and never as a wrong answer.
    missed = {f for f in case.defects if f in read and f not in found}
    invented = found - case.defects
    unread_defects = {f for f in case.defects if f not in read}
    unread_same = {f for f in case.same if f not in read}

    return v, by, read, found, missed, invented, unread_defects, unread_same


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    FIELDS = 7
    tot_read = tot_fields = 0
    tot_missed = tot_invented = 0
    tot_caught = tot_defects = tot_unreadable = 0

    for case in CASES:
        (v, by, read, found, missed, invented,
         unread_defects, unread_same) = run(case)

        tot_read += len(read)
        tot_fields += FIELDS
        tot_missed += len(missed)
        tot_invented += len(invented)
        # Only defects in fields it could read are defects it had a chance
        # at. Counting the rest against detection blames the comparator for a
        # vocabulary gap, which is the other number.
        tot_defects += len(case.defects & read)
        tot_caught += len(case.defects & found)
        tot_unreadable += len(case.defects - read)

        wrong = missed | invented
        mark = "  " if not wrong else "!!"
        print(f"{mark} {case.name}")
        print(f"     {case.why}")
        print(f"     read {len(read)}/{FIELDS} fields, verdict {v.status}"
              + (f" ({v.review_reason})" if v.review_reason else ""))
        if case.defects:
            print(f"     planted {sorted(case.defects)} -> caught "
                  f"{sorted(case.defects & found) or 'none'}")
        if unread_defects:
            print(f"     could not read (so could not judge): {sorted(unread_defects)}")
        if unread_same:
            print(f"     rewrites it could not read: {sorted(unread_same)}")
        if invented:
            print(f"     INVENTED a defect: {sorted(invented)}")
        if missed:
            print(f"     MISSED a defect it could read: {sorted(missed)}")
        if args.verbose:
            for f, c in by.items():
                state = {True: "agree", False: "DISAGREE", None: "unread"}[c.agree]
                print(f"        {f:<20} {state:<9} {str(c.si_value)[:26]:<28} "
                      f"vs {str(c.bl_value)[:26]}")
        print()

    print("=" * 70)
    print(f"  vocabulary read      : {tot_read}/{tot_fields} fields "
          f"({tot_read / tot_fields:.0%}) across {len(CASES)} unfamiliar cases")
    pct = f"{tot_caught / tot_defects:.0%}" if tot_defects else "n/a"
    print(f"  planted defects      : {tot_caught}/{tot_defects} caught ({pct}) "
          f"in fields it could read")
    if tot_unreadable:
        print(f"  never had a chance   : {tot_unreadable} planted defect(s) sat "
              f"in fields it could not read")
    print(f"  defects invented     : {tot_invented}")
    print(f"  defects waved through: {tot_missed}")
    print()

    # The safety property, and the only hard failure. Reading less of an
    # unfamiliar document is a coverage limit and is reported as one; judging
    # a field wrongly is the thing a desk would act on.
    if tot_invented or tot_missed:
        print("  FAIL - it judged a field it read incorrectly.")
        return 1
    print("  PASS - nothing it read was judged wrongly. Unread fields")
    print("         escalated rather than being guessed at.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
