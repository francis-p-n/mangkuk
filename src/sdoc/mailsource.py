"""Mail sources. The pipeline only ever talks to this interface.

The hackathon bundle is one implementation; a Microsoft Graph mailbox would be
another. Nothing downstream knows which one it is reading from.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
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
    """The organizers' docker server, same API over HTTP.

    A full run makes one listing request and then one per attachment - around
    260 against the supplied bundle - so the things that matter here are the
    ones that only show up at that volume:

    * **A timeout on every request.** Without one, a server that accepts the
      connection and then stalls hangs the run forever, with no output and
      nothing to debug.
    * **A retry.** One blip in 260 requests should not cost the whole run.
    * **`localhost` is resolved once, to an address.** On Windows `localhost`
      offers ::1 before 127.0.0.1, and a server bound only to IPv4 makes each
      connection pay the failed IPv6 attempt first - about two seconds, which
      turns a two-second run into a nine-minute one. The organizers' own
      instructions say `http://localhost:8080`, so this is worth handling
      rather than warning about.
    """

    TIMEOUT = 30
    ATTEMPTS = 3
    BACKOFF = 0.5      # seconds, multiplied by the attempt number
    PROBE_TIMEOUT = 0.5

    def __init__(self, base_url: str, timeout: float = TIMEOUT):
        self.base = self._resolve(base_url.rstrip("/"))
        self.timeout = timeout

    @staticmethod
    def _resolve(url: str) -> str:
        """Pin `localhost` to whichever stack actually answers."""
        parts = urllib.parse.urlsplit(url)
        if (parts.hostname or "").lower() != "localhost":
            return url
        port = parts.port or (443 if parts.scheme == "https" else 80)
        for family, _, _, _, addr in socket.getaddrinfo(
                "localhost", port, type=socket.SOCK_STREAM):
            try:
                with socket.socket(family, socket.SOCK_STREAM) as probe:
                    probe.settimeout(HttpMailSource.PROBE_TIMEOUT)
                    probe.connect(addr)
            except OSError:
                continue
            host = addr[0]
            if family == socket.AF_INET6:
                host = f"[{host}]"
            return urllib.parse.urlunsplit(
                parts._replace(netloc=f"{host}:{port}"))
        return url

    def _get(self, path: str) -> bytes:
        url = f"{self.base}/{path.lstrip('/')}"
        last: Exception | None = None
        for attempt in range(self.ATTEMPTS):
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as exc:
                # A 404 is an answer, not a blip; only retry server-side faults.
                if exc.code < 500:
                    raise
                last = exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
            if attempt + 1 < self.ATTEMPTS:
                time.sleep(self.BACKOFF * (attempt + 1))
        raise IOError(f"{url} failed after {self.ATTEMPTS} attempts: {last}") from last

    def emails(self) -> list[Email]:
        return [Email.from_record(rec) for rec in json.loads(self._get("emails"))]

    def read_bytes(self, att_path: str) -> bytes:
        return self._get(att_path)

    def sample_submission(self) -> dict:
        """The shape the server expects, from the server rather than from a
        local copy that may describe a different set of emails."""
        return json.loads(self._get("sample_submission"))

    def submit(self, submission: dict) -> dict:
        """POST the submission and return whatever the server says.

        The only step in the whole pipeline that writes anywhere outside this
        machine, so it is never called unless someone asks for it.
        """
        request = urllib.request.Request(
            f"{self.base}/submit",
            data=json.dumps(submission).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as r:
            return json.loads(r.read())


def open_source(location: str) -> MailSource:
    if location.startswith(("http://", "https://")):
        return HttpMailSource(location)
    return BundleMailSource(location)
