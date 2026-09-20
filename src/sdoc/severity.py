"""How much a wrong field actually costs, so the queue can be worked in order.

The comparator says *whether* seven fields agree. It says nothing about which
disagreement matters, and they are not close to equal: a wrong consignee can
put cargo in the hands of a party with no right to it, while a wrong container
count is an amended invoice. Working 46 corrections in email order treats
those the same.

The ranking below is a judgement call about consequence, not a measurement.
It is stated in one place, with the reason written next to each field, so an
operations team can disagree with it in one edit rather than argue with an
opaque score. That conversation is the point.
"""
from __future__ import annotations

from dataclasses import dataclass

# Rank 1 is the worst. The reason is the whole justification for the number,
# so the two live together and move together.
FIELD_RANK: dict[str, tuple[int, str]] = {
    "consignee": (
        1, "names who may take delivery - the wrong party could claim the cargo"),
    "shipper": (
        2, "names who holds title at origin, and who may amend the bill"),
    "port_of_discharge": (
        3, "cargo is discharged in the wrong country"),
    "gross_weight_kg": (
        4, "the declared weight a terminal verifies against - "
           "a misdeclaration can be refused at the gate"),
    "port_of_loading": (
        5, "affects routing and rating, and the carrier's own records"),
    "notify_party": (
        6, "nobody is told the cargo has arrived, so storage accrues"),
    "container_count": (
        7, "an amended bill and a corrected invoice"),
}

# Three bands, because a person triaging a queue can hold three categories in
# mind and not seven. The wording is the consequence, not the rank.
BANDS: tuple[tuple[str, int, str], ...] = (
    ("critical", 2, "the wrong party could take the cargo"),
    ("serious", 4, "cargo could be misrouted, or the declaration refused"),
    ("routine", 7, "an amendment, a delay and a corrected invoice"),
)

UNRANKED = (len(FIELD_RANK) + 1, "no consequence recorded for this field")


@dataclass(frozen=True)
class Severity:
    """The worst thing wrong with one draft."""

    band: str
    rank: int
    field: str | None
    reason: str
    count: int = 0

    @property
    def sort_key(self) -> tuple[int, int]:
        """Worst first; among equals, the draft with more wrong fields first."""
        return (self.rank, -self.count)


def rank_of(field_name: str) -> int:
    return FIELD_RANK.get(field_name, UNRANKED)[0]


def reason_for(field_name: str) -> str:
    return FIELD_RANK.get(field_name, UNRANKED)[1]


def band_for(rank: int) -> tuple[str, str]:
    for name, worst_rank, consequence in BANDS:
        if rank <= worst_rank:
            return name, consequence
    return BANDS[-1][0], BANDS[-1][2]


def assess(defect_fields: list[str]) -> Severity | None:
    """The severity of a draft, driven by its single worst field.

    A draft is as dangerous as the worst thing wrong with it. Three routine
    errors do not add up to a wrong consignee, so the fields are not summed -
    the count only breaks ties within a band.
    """
    if not defect_fields:
        return None
    worst = min(defect_fields, key=rank_of)
    rank = rank_of(worst)
    band, _ = band_for(rank)
    return Severity(band=band, rank=rank, field=worst,
                    reason=reason_for(worst), count=len(defect_fields))


def order(records: list) -> list:
    """Sort mismatching records worst-first. Anything unranked keeps its place."""
    def key(record):
        found = assess(list(getattr(record, "defect_fields", None)
                            or record.get("defect_fields", [])))
        return found.sort_key if found else (UNRANKED[0], 0)

    return sorted(records, key=key)
