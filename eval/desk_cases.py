#!/usr/bin/env python3
"""Does it behave like a documentation clerk would?

The bundle is one generator's idea of how these documents vary. A real desk
sees more: European decimal commas, terminal names that appear on one document
and not the other, "AND" written as "&", weights quoted in tonnes, port
aliases. Each case below states what an experienced clerk would say, and the
comparator has to agree.

Two kinds of failure, and they are not equally bad:

  FALSE ALARM  - flagged a difference that is not one. Costs trust and time.
  MISSED       - called two different things the same. Costs a wrong BL.

A missed unit change is the worst outcome this system can produce.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdoc.normalize import values_agree   # noqa: E402

AGREE, CONFLICT, UNDECIDABLE = "agree", "conflict", "undecidable"


@dataclass
class Case:
    field: str
    si: str
    bl: str
    expect: str
    why: str
    severity: str = "normal"   # "critical" for cases that must never be missed


CASES: list[Case] = [
    # ---- weights ------------------------------------------------------
    Case("gross_weight_kg", "21,577 KG", "21577", AGREE,
         "thousands separator only"),
    Case("gross_weight_kg", "21,577 KG", "21,577.00 KGS", AGREE,
         "trailing decimals from a spreadsheet export"),
    Case("gross_weight_kg", "131,058 KG", "131,058 KGS", AGREE,
         "KG vs KGS"),
    Case("gross_weight_kg", "21.577,00 KG", "21,577 KG", AGREE,
         "European decimal comma - Roxcel is in Vienna"),
    Case("gross_weight_kg", "21,577 KG", "23,114 KG", CONFLICT,
         "genuinely different weight"),
    Case("gross_weight_kg", "21,577 KG", "21,577 MT", CONFLICT,
         "tonnes vs kilograms - same digits, 1000x apart", "critical"),
    Case("gross_weight_kg", "21,577 KG", "21.577 MT", UNDECIDABLE,
         "'21.577' is 21577 in Europe and 21.577 elsewhere - readings disagree"),
    Case("gross_weight_kg", "21,577 KG", "21,577 TONS", UNDECIDABLE,
         "'ton' is short, long or metric - do not guess", "critical"),
    Case("gross_weight_kg", "132 MT", "132,000 KG", AGREE,
         "same weight, different unit - subject lines quote MT"),
    Case("gross_weight_kg", "N/A", "21,577 KG", UNDECIDABLE,
         "blank in the instruction"),

    # ---- containers ---------------------------------------------------
    Case("container_count", "6 x 40'HC", "6X40HC", AGREE,
         "spacing and quote stripped by an export"),
    Case("container_count", "6 x 40'HC", "6 x 40 HIGH CUBE", AGREE,
         "box type spelled out"),
    Case("container_count", "10 x 20'GP", "10 x 20'DV", AGREE,
         "GP and DV both mean a standard dry box"),
    Case("container_count", "3 x 40'HC", "4 x 40'HC", CONFLICT,
         "one more container", "critical"),
    Case("container_count", "6 x 20'GP", "6 x 40'GP", CONFLICT,
         "20ft vs 40ft", "critical"),
    Case("container_count", "6 x 20'GP", "6 x 20'RF", CONFLICT,
         "dry vs reefer", "critical"),

    # ---- parties ------------------------------------------------------
    Case("consignee", "MOORIM SP CO., LTD", "MOORIM SP CO., LTD.", AGREE,
         "trailing full stop"),
    Case("consignee", "ROXCEL TRADING GMBH", "Roxcel Trading G.m.b.H.", AGREE,
         "punctuated legal form"),
    Case("consignee", "AL GURG STATIONERY LLC", "AL GURG STATIONERY L.L.C.", AGREE,
         "punctuated LLC"),
    Case("consignee", "BALL & DOGGETT AUSTRALIA PTY LTD",
         "BALL AND DOGGETT AUSTRALIA PTY LTD", AGREE,
         "ampersand written out"),
    Case("consignee", "KPP-ANTALIS (SINGAPORE) PTE. LTD.",
         "KPP ANTALIS (SINGAPORE) PTE LTD", AGREE,
         "hyphen dropped"),
    Case("consignee", "EAST BRIGHT FZ-LLC", "UAB NOVAKOPA", CONFLICT,
         "different company entirely", "critical"),
    Case("consignee", "TO ORDER", "EAST BRIGHT FZ-LLC", CONFLICT,
         "negotiable BL turned into a straight one", "critical"),
    Case("consignee", "CLIFFORD PAPER INC", "CLIFFORD PAPER INC.", AGREE,
         "abbreviation full stop"),

    # ---- ports --------------------------------------------------------
    Case("port_of_loading", "SINGAPORE", "SINGAPORE (SGSIN)", AGREE,
         "one side omits the code"),
    Case("port_of_loading", "PORT KLANG (WESTPORT), MALAYSIA (MYPKG)",
         "PORT KLANG, MALAYSIA (MYPKG)", AGREE,
         "terminal named on one document only"),
    Case("port_of_loading", "NHAVA SHEVA, INDIA (INNSA)",
         "JAWAHARLAL NEHRU (NHAVA SHEVA), INDIA (INNSA)", AGREE,
         "official name vs common name, same UN/LOCODE"),
    Case("port_of_discharge", "PORT KLANG, MALAYSIA (MYPKG)",
         "PORT KELANG, MALAYSIA (MYPKG)", AGREE,
         "spelling variant, same code"),
    Case("port_of_discharge", "MOMBASA, KENYA (KEMBA)",
         "TUTICORIN, INDIA (KEMBA)", CONFLICT,
         "code kept, port swapped - the bundle's own trap", "critical"),
    Case("port_of_discharge", "FREMANTLE, AUSTRALIA (AUFRE)",
         "FREMANTLE, AUSTRALIA (AUBNE)", CONFLICT,
         "same city, wrong code", "critical"),
    Case("port_of_discharge", "BUSAN, SOUTH KOREA", "CEBU, PHILIPPINES", CONFLICT,
         "different destination", "critical"),
]


def main() -> int:
    width = max(len(c.why) for c in CASES) + 2
    failures: list[tuple[Case, str]] = []

    print(f"{'field':<18} {'expected':<12} {'got':<12} case")
    print("-" * (44 + width))
    for case in CASES:
        result = values_agree(case.field, case.si, case.bl)
        got = {True: AGREE, False: CONFLICT, None: UNDECIDABLE}[result]
        ok = got == case.expect
        if not ok:
            failures.append((case, got))
        mark = " " if ok else "X"
        flag = "  <<< CRITICAL" if (not ok and case.severity == "critical") else ""
        print(f"{mark}{case.field:<17} {case.expect:<12} {got:<12} {case.why}{flag}")

    print()
    missed = [(c, g) for c, g in failures if c.expect == CONFLICT]
    alarms = [(c, g) for c, g in failures if c.expect == AGREE and g == CONFLICT]
    print(f"cases        : {len(CASES)}")
    print(f"passing      : {len(CASES) - len(failures)}")
    print(f"MISSED       : {len(missed)}  (called two different things the same)")
    print(f"FALSE ALARMS : {len(alarms)}  (flagged a difference that is not one)")

    if missed:
        print("\nMISSED - these put a wrong value on a bill of lading:")
        for c, g in missed:
            print(f"  {c.field}: {c.si!r} vs {c.bl!r}")
            print(f"      {c.why} -> reported {g}")
    if alarms:
        print("\nFALSE ALARMS - these send a clerk chasing nothing:")
        for c, g in alarms:
            print(f"  {c.field}: {c.si!r} vs {c.bl!r}")
            print(f"      {c.why}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
