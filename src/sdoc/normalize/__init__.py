"""Per-field normalization and equality. No model involved.

Comparison is the part that must be reproducible, testable and explainable,
so it is ordinary code. The model's job upstream is to *locate* values; this
package decides whether two located values mean the same thing.

One module per field type, because the rules for a company name and the rules
for a weight have nothing in common and change for different reasons:

    parties.py     shipper, consignee, notify party
    ports.py       loading and discharge ports
    containers.py  counts and box types
    weights.py     gross weight, in any unit
    numbers.py     reading a written quantity either way round
    text.py        shared string handling

The rules are tuned against `eval/desk_cases.py`, which encodes what an
experienced documentation clerk would call a match. Two directions of error,
weighted very differently:

  a MISS (two different things called the same) puts a wrong value on a bill
  of lading, and is the worst thing this system can do;
  a FALSE ALARM (a difference reported that is not one) costs a clerk a few
  minutes and, repeated often enough, costs their trust in the tool.

Where a rule cannot be made safe in both directions it errs toward flagging.
"""
from __future__ import annotations

from .containers import CONTAINER_KINDS, Containers, parse_containers
from .numbers import candidates as _number_candidates, parse as _parse_number
from .parties import COMPANY_SUFFIXES, norm_party
from .ports import Port, names_compatible as _names_compatible, parse_port
from .text import _clean, clean, edit_distance as _edit_distance
from .weights import AMBIGUOUS_UNITS, WEIGHT_UNITS, parse_weight, weight_candidates
from . import containers as _containers, parties as _parties, ports as _ports, weights as _weights

__all__ = [
    "values_agree",
    "norm_party", "parse_port", "parse_containers", "parse_weight",
    "weight_candidates", "Port", "Containers",
    "COMPANY_SUFFIXES", "CONTAINER_KINDS", "WEIGHT_UNITS", "AMBIGUOUS_UNITS",
    "clean",
]

# Which module owns which field. Adding a compared field is one line here and
# one new module, not a new branch in a growing if-chain.
_RULES = {
    "shipper": _parties.agree,
    "consignee": _parties.agree,
    "notify_party": _parties.agree,
    "port_of_loading": _ports.agree,
    "port_of_discharge": _ports.agree,
    "container_count": _containers.agree,
    "gross_weight_kg": _weights.agree,
}


def values_agree(field_name: str, a: str, b: str) -> bool | None:
    """True = same, False = genuine conflict, None = cannot tell from these."""
    rule = _RULES.get(field_name)
    if rule is None:
        return clean(a) == clean(b)
    return rule(a, b)
