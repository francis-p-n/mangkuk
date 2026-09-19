"""Pull the seven compared fields out of a document, with evidence.

The SI and the BL label the same thing differently — 66 distinct labels appear
across the corpus for these seven concepts. We align by meaning, never by
header text. Every extracted value carries the exact source line that produced
it, so a human can check the machine instead of trusting it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

# Ordered: first rule that matches wins. Order is load-bearing —
# "Notify Party/Intermediate Consignee" must resolve to notify_party, and
# "Kinds of Packages; Description of Goods" must not resolve to containers.
LABEL_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("notify_party",      ("notify",)),
    ("consignee",         ("consignee", "to the order of")),
    ("shipper",           ("shipper", "exporter", "seller")),
    ("port_of_loading",   ("port of loading", "load port", "pol")),
    ("port_of_discharge", ("port of discharge", "discharge port", "pod")),
    ("container_count",   ("container",)),
    ("gross_weight_kg",   ("gross weight", "gross wt")),
]

_ASCII = re.compile(r"[^\x00-\x7f]")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """'Gross Weight毛重(KGS)' -> 'gross weight kgs'."""
    s = _ASCII.sub(" ", label).lower()
    s = _NONWORD.sub(" ", s)
    return _WS.sub(" ", s).strip()


def label_to_field(label: str) -> str | None:
    norm = normalize_label(label)
    if not norm:
        return None
    for name, markers in LABEL_RULES:
        for m in markers:
            # Short codes (pol/pod) must match the whole label, not a substring,
            # or 'Port of Loading' would hit 'pol' inside another word.
            if len(m) <= 3:
                if norm == m:
                    return name
            elif m in norm:
                return name
    return None


@dataclass
class Extracted:
    """One field value plus where it came from."""

    value: str
    label: str
    line_no: int
    raw_line: str
    detail: str = ""     # continuation line, e.g. a party's address


@dataclass
class FieldSet:
    values: dict[str, Extracted] = dc_field(default_factory=dict)

    def get(self, name: str) -> Extracted | None:
        return self.values.get(name)

    @property
    def missing(self) -> list[str]:
        return [f for f in FIELDS if f not in self.values]


def _is_continuation(line: str) -> bool:
    return bool(line) and line[0] in " \t" and ":" not in line.split("  ")[-1][:40]


def plausible(name: str, value: str) -> bool:
    """Cheap sanity guard for values found without a colon to anchor them."""
    from .normalize import parse_containers, parse_weight

    if name == "gross_weight_kg":
        return parse_weight(value) is not None
    if name == "container_count":
        return parse_containers(value) is not None
    return len(value) > 2 and any(ch.isalpha() for ch in value)


def extract_fields(text: str) -> FieldSet:
    """Two passes, most reliable signal first.

    Pass 1 reads 'Label: value' lines. Pass 2 handles block layouts, where the
    label sits on its own line and the value follows underneath — the shape PDF
    extraction produces.

    The order is load-bearing. A PDF bill of lading has a container table whose
    header reads 'GROSS WEIGHT (KG)' with container numbers underneath, and the
    real total further down as 'TOTAL Gross Weight (KG): 131,322 KG'. Reading
    colon-anchored values first means the total wins and the table header is
    skipped as already-filled.
    """
    fs = _pass_labelled(text)
    _pass_block(text, fs)
    return fs


def _pass_labelled(text: str) -> FieldSet:
    """Parse 'Label: value' lines, keeping the first value seen per field.

    First-wins matters: a BL may repeat a party lower down in freight terms,
    and the title-block occurrence is the authoritative one.
    """
    fs = FieldSet()
    lines = text.splitlines()
    last_field: str | None = None

    for i, raw in enumerate(lines):
        if not raw.strip():
            last_field = None
            continue

        # Indented, colon-free line directly under a field = that field's address.
        if last_field and raw[:1] in " \t" and ":" not in raw:
            got = fs.values.get(last_field)
            if got and not got.detail:
                got.detail = raw.strip()
            continue

        if ":" not in raw:
            last_field = None
            continue

        label, _, value = raw.partition(":")
        name = label_to_field(label)
        value = value.strip()
        if not name or not value:
            last_field = None
            continue

        if name not in fs.values:
            # Flattened spreadsheet/table rows arrive as 'NAME | ADDRESS'; keep the
            # same shape as the text files, where the address is a continuation line.
            head, _, tail = value.partition(" | ")
            fs.values[name] = Extracted(
                value=head.strip(),
                label=label.strip(),
                line_no=i + 1,
                raw_line=raw.rstrip(),
                detail=tail.strip(),
            )
            last_field = name
        else:
            last_field = None

    return fs


def _pass_block(text: str, fs: FieldSet) -> None:
    """Fill still-missing fields from a label-line / value-line-below layout."""
    lines = text.splitlines()

    for i, raw in enumerate(lines):
        label = raw.strip()
        if not label or ":" in label:
            continue
        name = label_to_field(label)
        if not name or name in fs.values:
            continue

        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            continue

        value = lines[j].strip()
        # The next line being another label means this field has no value here.
        if ":" in value or label_to_field(value) or not plausible(name, value):
            continue

        detail_parts: list[str] = []
        for k in range(j + 1, min(j + 5, len(lines))):
            nxt = lines[k].strip()
            if not nxt or ":" in nxt or label_to_field(nxt):
                break
            detail_parts.append(nxt)

        fs.values[name] = Extracted(
            value=value,
            label=label,
            line_no=j + 1,
            raw_line=lines[j].rstrip(),
            detail="; ".join(detail_parts),
        )


# Context shown on the shipment card. Never compared — these exist so a person
# can recognise the shipment, not so the machine can judge it.
CONTEXT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("vessel",     ("vessel", "export carrier", "ocean vessel")),
    ("voyage",     ("voyage", "voy no", "voy")),
    ("commodity",  ("commodity", "description of goods", "description")),
    ("bl_number",  ("bill of lading no", "b l no", "b l number", "bl no")),
    ("booking",    ("booking",)),
    ("oc_number",  ("oc no",)),
]


def extract_context(text: str) -> dict[str, str]:
    """Descriptive fields for the shipment card, first occurrence wins."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        label, _, value = raw.partition(":")
        norm, value = normalize_label(label), value.strip()
        if not norm or not value or label_to_field(label):
            continue
        for name, markers in CONTEXT_RULES:
            if name in found:
                continue
            if any(norm == m or norm.startswith(m) or m in norm for m in markers):
                found[name] = value
                break
    return found
