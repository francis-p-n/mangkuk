"""Mail sources. The pipeline only ever talks to this interface.

The hackathon bundle is one implementation; a Microsoft Graph mailbox would be
another. Nothing downstream knows which one it is reading from.
"""
from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class Email:
    email_id: str
    sender: str
    subject: str
    body: str
    attachments: list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, rec: dict) -> "Email":
        return cls(
            email_id=rec["email_id"],
            sender=rec.get("from", ""),
            subject=rec.get("subject", ""),
            body=rec.get("body", ""),
            attachments=list(rec.get("attachments", [])),
        )

    @property
    def domain(self) -> str:
        return self.sender.rsplit("@", 1)[-1].lower() if "@" in self.sender else ""


class MailSource(ABC):
    """Read-only view of a mailbox."""

    @abstractmethod
    def emails(self) -> list[Email]: ...

    @abstractmethod
    def read_bytes(self, att_path: str) -> bytes: ...

    def __iter__(self) -> Iterator[Email]:
        return iter(self.emails())


class BundleMailSource(MailSource):
    """The static participant bundle: inbox/*.json + attachments/."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def emails(self) -> list[Email]:
        inbox = self.root / "inbox"
        return [
            Email.from_record(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(inbox.glob("email_*.json"))
        ]

    def read_bytes(self, att_path: str) -> bytes:
        return (self.root / att_path).read_bytes()


class HttpMailSource(MailSource):
    """The organizers' docker server, same API over HTTP."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def emails(self) -> list[Email]:
        with urllib.request.urlopen(f"{self.base}/emails") as r:
            return [Email.from_record(rec) for rec in json.loads(r.read())]

    def read_bytes(self, att_path: str) -> bytes:
        with urllib.request.urlopen(f"{self.base}/{att_path.lstrip('/')}") as r:
            return r.read()


def open_source(location: str) -> MailSource:
    if location.startswith(("http://", "https://")):
        return HttpMailSource(location)
    return BundleMailSource(location)
