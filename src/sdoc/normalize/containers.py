"""Container counts and box types."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Box types that mean the same thing on a container. A standard dry box is
# written GP, DV, DC or SD depending on the carrier; a high cube is HC, HQ or
# spelled out. FCL is deliberately kept distinct - it describes the load, not
# the box, and treating it as an alias would hide a real change.
CONTAINER_KINDS = {
    "gp": "DRY", "dv": "DRY", "dc": "DRY", "sd": "DRY", "std": "DRY",
    "hc": "HC", "hq": "HC", "high": "HC", "hicube": "HC",
    "rf": "REEF", "re": "REEF", "reef": "REEF", "rh": "REEF",
    "ot": "OT", "fr": "FR", "tk": "TANK", "fcl": "FCL",
}

_CONTAINERS = re.compile(r"(\d+)\s*[xX]\s*(\d+)\s*'?\s*([A-Za-z]+)?")


@dataclass(frozen=True)
class Containers:
    count: int
    size: str
    kind: str


def parse_containers(value: str) -> Containers | None:
    m = _CONTAINERS.search(value)
    if not m:
        digits = re.search(r"\d+", value)
        return Containers(int(digits.group()), "", "") if digits else None
    raw_kind = (m.group(3) or "").lower()
    kind = CONTAINER_KINDS.get(raw_kind, raw_kind.upper())
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
