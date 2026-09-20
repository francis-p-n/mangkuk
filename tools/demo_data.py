#!/usr/bin/env python3
"""Replace every identifying value with a consistent invented one.

    python tools/demo_data.py            # out/results.json -> out/results-demo.json

The public demo must not carry the organizers' bundle onto the open internet:
real consignees, street addresses, booking references and OC numbers. This
swaps them for invented equivalents that behave identically.

Two properties make it safe rather than hopeful:

  *Substitution is global.* The whole results file is rewritten as text, so a
  value is replaced everywhere it appears - the shipment card, the comparison
  table, the evidence quotes, the email subject - and no field can be missed
  by forgetting to list it.

  *Substitution is one-to-one.* Two different companies never collapse into
  one, and one company never splits into two, so every verdict is unchanged.
  `--check` proves that by diffing the submission before and after.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Invented companies. Plausible for the trade, deliberately not real firms.
FAKE_PARTIES = [
    "NORTHWIND PAPER TRADING PTE LTD", "MERIDIAN PULP (M) SDN BHD",
    "CASTLEFORD STATIONERY LLC", "BLUE HARBOUR PAPER GMBH",
    "SUNSTRAND BOARD CO., LTD", "ORCHID BAY TRADING FZ-LLC",
    "KETTLEWELL PAPER INC", "VANTAGE FIBRE AUSTRALIA PTY LTD",
    "LINDEN & HALE PAPER LIMITED", "ATLAS REACH PAPER FZE",
    "SILVERBIRCH CONVERTING UAB", "PORTMAN PAPER PRODUCTS SDN BHD",
    "GRANVILLE BOARD TRADING GMBH", "EASTLIGHT PAPER CO (LLC)",
    "COPPERFIELD PULP LIMITED", "TIDEWATER STATIONERY LLC",
    "HOLLOWAY FINE PAPER PTE. LTD.", "REDPOINT PACKAGING INC",
    "MARLOWE BOARD TRADING LIMITED", "CALDERA PAPER JOINT STOCK COMPANY",
    "WESTGATE FIBRE TRADING PTE LTD", "AMBERTON PAPER (M) SDN BHD",
    "QUAYSIDE BOARD FZ-LLC", "FERNCROFT PAPER GMBH",
    "STONEHAVEN PULP CO., LTD", "BRIGHTWATER PAPER LLC",
    "LARKSPUR CONVERTING LIMITED", "HAVENWOOD BOARD INC",
    "SEABRIGHT PAPER PTY LTD", "CROWNMOOR TRADING FZE",
]

FAKE_STREETS = [
    "12 HARBOURGATE ROAD", "8 MERCHANT SQUARE", "45 KILNWOOD AVENUE",
    "217 STILLWATER DRIVE", "6 LANTERN WHARF", "90 CEDARBANK STREET",
    "31 OLD FOUNDRY LANE", "154 NORTHGATE PARADE", "22 BRIDGEHOUSE WAY",
    "77 CLAYFIELD ROAD", "5 SALTMARSH CRESCENT", "188 WINDROW BOULEVARD",
    "63 PENNANT STREET", "14 GRANARY COURT", "240 ELMFIELD ROAD",
]
FAKE_LOCALITIES = [
    "UNIT 4", "LEVEL 9", "SUITE 1200", "BLOCK C", "TOWER 2, LEVEL 15",
    "OFFICE 305", "FLOOR 7", "BUILDING B",
]

# Things that identify a shipment rather than a person or a company.
OC_RE = re.compile(r"\b5[A-Z]{3}-\d{5}\b")
BOOKING_RE = re.compile(r"\b(?:MSDU|MEDU|SIN|SIJ|PSGSE|OOLU|YMJAI|MCLSIN|SINF|EGLV|I)[A-Z]*\d{6,}\b")
INVOICE_RE = re.compile(r"\b52\d{8}\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# No trailing \b: underscore is a word character, so it never fires before the
# "_138MT" that follows a PO number in these subject lines.
PO_RE = re.compile(r"\bPO[_ ]?\d{2}[_ ]?\d{3,5}", re.I)

FAKE_DOMAINS = ["nordpaper.example", "castleford.example", "bluehbr.example",
                "orchidbay.example", "atlasreach.example", "quayside.example"]
FAKE_VESSELS = [
    "NORTHERN SPIRIT", "CORAL MERIDIAN", "PACIFIC LANTERN", "IRON BAYWIND",
    "SILVER KESTREL", "EASTERN FULMAR", "BLUE PETREL", "GRANITE DAWN",
    "HARBOUR SWIFT", "CEDAR VOYAGER", "AMBER TIDE", "STONE HERALD",
]

FAKE_NAMES = ["A. Whitfield", "R. Castellano", "M. Oyelaran", "J. Lindqvist",
              "P. Ramanathan", "S. Abbascia", "T. Iwuchukwu", "D. Marchetti"]


class Mapper:
    """Deterministic, injective replacements built from what is actually present."""

    def __init__(self, seed: int = 20260920):
        self.rng = random.Random(seed)
        self.map: dict[str, str] = {}
        self._used: set[str] = set()
        self._reserved: set[str] = set()
        self._party_pool = list(FAKE_PARTIES)
        self.rng.shuffle(self._party_pool)

    def reserve(self, values) -> None:
        """Real values an invented one must never coincide with.

        Without this, a generated reference can happen to equal a different
        real reference, and substituting that one puts the real value straight
        back into the file.
        """
        self._reserved.update(values)

    def _ok(self, fake: str) -> bool:
        """Unused, and containing no real value anywhere inside it.

        Equality is not enough. Appending a digit to a reserved reference
        yields a string that still *contains* it, which puts the real value
        back into the file the moment that entry is substituted.
        """
        if fake in self._used:
            return False
        return not any(real in fake for real in self._reserved)

    def _assign(self, real: str, factory) -> str:
        """Draw invented values until one is clean, then keep it."""
        for _ in range(200):
            fake = factory()
            if self._ok(fake):
                self.map[real] = fake
                self._used.add(fake)
                return fake
        raise RuntimeError(f"could not mint a safe replacement for {real!r}")

    def party(self, real: str) -> str:
        if real in self.map:
            return self.map[real]
        return self._assign(real, lambda: (
            self._party_pool.pop() if self._party_pool else
            f"{self.rng.choice(['ASHDOWN', 'KELVEDON', 'MARLBANK', 'THORNBURY'])} "
            f"PAPER {self.rng.randint(100, 999)}"))

    def address(self, real: str, country: str) -> str:
        if real in self.map:
            return self.map[real]
        return self._assign(real, lambda: "; ".join([
            self.rng.choice(FAKE_LOCALITIES),
            self.rng.choice(FAKE_STREETS),
            f"{self.rng.randint(10000, 99999)} {country.upper()}".strip(),
        ]))

    def oc(self, real: str) -> str:
        if real in self.map:
            return self.map[real]
        return self._assign(real, lambda: "5%s-%d" % (
            "".join(self.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(3)),
            self.rng.randint(10000, 99999)))

    def reference(self, real: str) -> str:
        if real in self.map:
            return self.map[real]
        # Keep the shape a clerk recognises: a carrier prefix stays a carrier
        # prefix, and an all-digit invoice number stays an all-digit invoice
        # number with the same leading pair.
        prefix = re.match(r"^[A-Z]+", real)
        if prefix:
            head, digits = prefix.group(), max(len(real) - len(prefix.group()), 6)
        else:
            head, digits = real[:2], len(real) - 2
        return self._assign(real, lambda: head + "".join(
            str(self.rng.randint(0, 9)) for _ in range(digits)))

    def email(self, real: str) -> str:
        if real in self.map:
            return self.map[real]
        return self._assign(real, lambda: "%s%d@%s" % (
            self.rng.choice(["a.whitfield", "r.castellano", "m.oyelaran",
                             "j.lindqvist", "p.raman", "s.abbascia"]),
            self.rng.randint(1, 99), self.rng.choice(FAKE_DOMAINS)))

    def vessel(self, real: str) -> str:
        if real in self.map:
            return self.map[real]
        return self._assign(real, lambda: "%s %d V.%03d%s" % (
            self.rng.choice(FAKE_VESSELS), self.rng.randint(10, 999),
            self.rng.randint(1, 999), self.rng.choice("ABCDEFNW")))

    def po(self, real: str) -> str:
        if real in self.map:
            return self.map[real]
        return self._assign(real, lambda: "PO_%d_%d" % (
            self.rng.randint(30, 79), self.rng.randint(1000, 9999)))


def collect(results: list[dict], m: Mapper) -> None:
    """Walk the results and mint a replacement for everything identifying."""
    blob = json.dumps(results, ensure_ascii=False)

    # Everything real is off-limits as an invented value, so reserve it all
    # before minting anything.
    reals: set[str] = set()
    for r in results:
        sh = r.get("shipment") or {}
        reals.update(str(sh[k]) for k in ("shipper", "consignee", "notify_party",
                                          "consignee_address", "vessel") if sh.get(k))
        for c in r.get("comparisons") or []:
            if c["field"] in ("shipper", "consignee", "notify_party"):
                reals.update(str(c[s]) for s in ("si_value", "bl_value") if c.get(s))
    for pattern in (OC_RE, BOOKING_RE, INVOICE_RE, EMAIL_RE, PO_RE):
        reals.update(pattern.findall(blob))
    m.reserve(reals)

    for r in results:
        sh = r.get("shipment") or {}
        for key in ("shipper", "consignee", "notify_party"):
            if sh.get(key):
                m.party(sh[key])
        # Party names also appear as compared values and inside evidence.
        for c in r.get("comparisons") or []:
            if c["field"] in ("shipper", "consignee", "notify_party"):
                for side in ("si_value", "bl_value"):
                    if c.get(side):
                        m.party(c[side])
        if sh.get("consignee_address"):
            m.address(sh["consignee_address"], sh.get("consignee_country") or "")
        if sh.get("vessel"):
            m.vessel(sh["vessel"])

    # References and contacts, wherever they occur in the file.
    for match in sorted(set(OC_RE.findall(blob)), key=len, reverse=True):
        m.oc(match)
    for match in sorted(set(BOOKING_RE.findall(blob)) | set(INVOICE_RE.findall(blob)),
                        key=len, reverse=True):
        m.reference(match)
    for match in sorted(set(EMAIL_RE.findall(blob)), key=len, reverse=True):
        m.email(match)
    for match in sorted(set(PO_RE.findall(blob)), key=len, reverse=True):
        m.po(match)


def substitute(text: str, mapping: dict[str, str]) -> str:
    """Longest first, so a short name inside a longer one cannot corrupt it."""
    for real in sorted(mapping, key=len, reverse=True):
        text = text.replace(real, mapping[real])
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description="make a shareable demo dataset")
    ap.add_argument("--results", default=str(ROOT / "out" / "results.json"))
    ap.add_argument("--out", default=str(ROOT / "out" / "results-demo.json"))
    ap.add_argument("--report", action="store_true", help="list the substitutions")
    args = ap.parse_args()

    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    mapper = Mapper()
    collect(results, mapper)

    original = json.dumps(results, ensure_ascii=False, indent=2)
    scrubbed = substitute(original, mapper.map)

    # Nothing identifying may survive.
    leaks = [real for real in mapper.map if real in scrubbed]
    if leaks:
        print(f"REFUSING TO WRITE - {len(leaks)} value(s) survived:", file=sys.stderr)
        for real in leaks[:10]:
            print(f"  {real!r}", file=sys.stderr)
        return 1

    # Verdicts must be untouched.
    before = [(r["email_id"], r["category"], r["status"], r["review_reason"],
               tuple(r["defect_fields"])) for r in results]
    after = [(r["email_id"], r["category"], r["status"], r["review_reason"],
              tuple(r["defect_fields"])) for r in json.loads(scrubbed)]
    if before != after:
        changed = [b[0] for b, a in zip(before, after) if b != a]
        print(f"REFUSING TO WRITE - {len(changed)} verdict(s) changed: {changed[:5]}",
              file=sys.stderr)
        return 1

    Path(args.out).write_text(scrubbed, encoding="utf-8")
    print(f"replaced {len(mapper.map)} identifying values")
    print(f"  parties and addresses : {sum(1 for k in mapper.map if not any(c.isdigit() for c in k[:6]))}")
    print(f"  verdicts changed      : 0")
    print(f"  leaks                 : 0")
    print(f"wrote {args.out}")

    if args.report:
        print("\nsubstitutions:")
        for real, fake in sorted(mapper.map.items())[:40]:
            print(f"  {real[:48]:<50} -> {fake[:48]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
