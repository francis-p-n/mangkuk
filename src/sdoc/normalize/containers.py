"""Container counts and box types."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Box types that mean the same thing on a container. A standard dry box is
# written GP, DV, DC or SD depending on the carrier; a high cube is HC, HQ or
# spelled out. FCL is deliberately kept distinct - it describes the load, not
# the box, and treating it as an alias would hide a real change.
#
# RH is a reefer HIGH CUBE and is not the same box as an RF: different height,
# different cubic capacity, different equipment. It had been folded in with
# the reefers, which meant a draft that changed one for the other passed
# silently - the same error the table already refuses to make between GP and
# HC, in the direction that matters more.
#
# The spelled-out forms are here because a code absent from this table passes
# through raw, so "PL" against "PLATFORM" compared as two different boxes and
# sent a clerk chasing a difference that was only spelling.
CONTAINER_KINDS = {
    "gp": "DRY", "dv": "DRY", "dc": "DRY", "sd": "DRY", "std": "DRY",
    "dry": "DRY", "general": "DRY", "standard": "DRY",

    "hc": "HC", "hq": "HC", "high": "HC", "hicube": "HC", "highcube": "HC",

    "rf": "REEF", "re": "REEF", "reef": "REEF", "reefer": "REEF",
    "rt": "REEF", "refrigerated": "REEF",
    "rh": "REEF_HC", "reeferhc": "REEF_HC",

    "ot": "OT", "opentop": "OT", "ut": "OT",
    "fr": "FR", "flatrack": "FR", "pl": "FR", "platform": "FR",
    "tk": "TANK", "tn": "TANK", "tank": "TANK",
    "vh": "VENT", "ventilated": "VENT",
    "bu": "BULK", "bulk": "BULK",

    "fcl": "FCL",
}

# Air freight unit load devices. These are not ISO containers and this tool
# does not know how to compare them: an AKE is a contoured LD3, a PMC is a
# pallet, and nothing here models the difference. They matter because the
# parser reads "3 x AKE" as a count of three and nothing else, so two
# different ULDs compared as equal - a silent wrong answer on a document this
# tool should not be judging at all. Recognised only so they can be refused.
_ULD = re.compile(
    r"^(a[a-z]{2}|p[a-z]{2}|ld\d+|dp[a-z]|rk[a-z]|kmp|mdp)$", re.I
)

# The kind may be a code ("HC") or spelled out in two words ("HIGH CUBE",
# "OPEN TOP", "FLAT RACK"). Two words at most: past that it stops being the
# box type and starts being the description of goods that follows it.
_CONTAINERS = re.compile(
    r"(\d+)\s*[xX]\s*(\d+)\s*'?\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)?"
)


@dataclass(frozen=True)
class Containers:
    count: int
    size: str
    kind: str


def parse_containers(value: str) -> Containers | None:
    m = _CONTAINERS.search(value)
    if not m:
        # A count with no box: "3 x AKE" parses here, and an air ULD read as a
        # bare count is worse than no reading at all, because two different
        # ULDs then agree on the count and nothing else is left to disagree.
        if _ULD.search(re.sub(r"^\s*\d+\s*[xX]?\s*", "", value.strip())):
            return None
        digits = re.search(r"\d+", value)
        return Containers(int(digits.group()), "", "") if digits else None
    raw_kind = (m.group(3) or "").strip().lower()
    squashed = re.sub(r"\s+", "", raw_kind)
    if _ULD.match(squashed):
        return None

    # "HIGH CUBE" before "HIGH": the two-word form is the more specific
    # reading, and falling back to the first word alone keeps "40'HC SAID TO
    # CONTAIN" from being read as a box type nobody uses.
    kind = CONTAINER_KINDS.get(squashed)
    if kind is None:
        first = raw_kind.split()[0] if raw_kind else ""
        kind = CONTAINER_KINDS.get(first, first.upper())
    return Containers(int(m.group(1)), m.group(2), kind)


def agree(a: str, b: str) -> bool | None:
    ca, cb = parse_containers(a), parse_containers(b)
    if ca is None or cb is None:
        return None
    if ca.count != cb.count:
        return False
    if ca.size and cb.size and ca.size != cb.size:
        return False
    if ca.kind and cb.kind and ca.kind != cb.kind:
        return False
    return True
