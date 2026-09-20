"""The two reading passes: colon-anchored first, block layout second."""
from __future__ import annotations

from .aliases import label_to_field
from .model import Extracted, FieldSet
from .placeholders import is_placeholder
from .plausibility import plausible

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
        if not name or is_placeholder(value):
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
        if ":" in value or label_to_field(value) or is_placeholder(value):
            continue
        if not plausible(name, value):
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
