"""Reading a model's reply, defensively.

A model may wrap JSON in prose or a code fence, return nothing, or be cut off
mid-object. None of that should raise; an unreadable reply is an abstention.
"""
from __future__ import annotations

import json
import re

_WS = re.compile(r"\s+")


def _squash(text: str) -> str:
    """Whitespace-insensitive form, so a quote still matches across line wraps."""
    return _WS.sub(" ", text).strip().lower()


def _parse_json_object(raw: str) -> dict:
    """Models sometimes wrap JSON in prose or a code fence. Take the object."""
    if not raw or not raw.strip():
        return {}
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
