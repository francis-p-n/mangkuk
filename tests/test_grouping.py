"""Emails are vertices, references are edges, a shipment is a component.

The corpus cannot test any of this. Every reference in it belongs to exactly
one email - 388 OC numbers across 388 emails, 222 bookings across 222 - so all
520 components have size one and the grouping is never asked to do anything.
The logic still has to be right for the day real threaded mail arrives, which
is what these are for.

This mirrors web/lib/shipments.ts. The rule is the same in both: a shared
reference groups, resemblance never does.
"""
from __future__ import annotations

import pytest

from conftest import DATA_DIR
from sdoc.mailsource import BundleMailSource
from sdoc.pipeline import run


@pytest.fixture(scope="module")
def results():
    return {r.email_id: r for r in run(BundleMailSource(DATA_DIR))}


def references_of(email: dict) -> list[str]:
    return [v.strip() for v in (email.get("oc_number"), email.get("booking_ref"))
            if isinstance(v, str) and v.strip()]


def components_of(emails: list[dict]) -> dict[str, str]:
    """Union-find over emails and the references they carry."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for e in emails:
        v = f"email:{e['email_id']}"
        find(v)
        for ref in references_of(e):
            union(v, f"ref:{ref}")

    return {e["email_id"]: find(f"email:{e['email_id']}") for e in emails}


def folders(emails: list[dict]) -> list[set[str]]:
    comp = components_of(emails)
    out: dict[str, set[str]] = {}
    for e in emails:
        out.setdefault(comp[e["email_id"]], set()).add(e["email_id"])
    return sorted(out.values(), key=lambda s: sorted(s)[0])


def email(eid, oc=None, booking=None):
    return {"email_id": eid, "oc_number": oc, "booking_ref": booking}


class TestIsolatedVertices:
    def test_an_email_with_no_reference_is_its_own_file(self):
        got = folders([email("email_001"), email("email_002")])
        assert got == [{"email_001"}, {"email_002"}]

    def test_unreferenced_emails_are_never_filed_together(self):
        """Otherwise 123 unrelated notices become one folder."""
        got = folders([email(f"email_{i:03}") for i in range(1, 6)])
        assert all(len(f) == 1 for f in got)
        assert len(got) == 5


class TestSharedReferences:
    def test_a_shared_oc_number_groups(self):
        got = folders([email("a", oc="OC-1"), email("b", oc="OC-1")])
        assert got == [{"a", "b"}]

    def test_a_shared_booking_groups(self):
        got = folders([email("a", booking="BK-9"), email("b", booking="BK-9")])
        assert got == [{"a", "b"}]

    def test_different_references_stay_apart(self):
        got = folders([email("a", oc="OC-1"), email("b", oc="OC-2")])
        assert got == [{"a"}, {"b"}]


class TestBridges:
    """The case single-key grouping gets wrong.

    213 of 520 emails in the corpus carry both references, so a bridge is
    structurally present even though nothing in the corpus repeats a
    reference for one to span.
    """

    def test_an_email_carrying_both_joins_two_references(self):
        got = folders([
            email("a", oc="OC-1"),                  # names only the OC
            email("b", oc="OC-1", booking="BK-9"),  # the bridge
            email("c", booking="BK-9"),             # names only the booking
        ])
        assert got == [{"a", "b", "c"}], "a and c connect only through b"

    def test_without_the_bridge_they_are_separate(self):
        got = folders([email("a", oc="OC-1"), email("c", booking="BK-9")])
        assert got == [{"a"}, {"c"}]

    def test_a_chain_of_bridges_forms_one_file(self):
        got = folders([
            email("a", oc="OC-1"),
            email("b", oc="OC-1", booking="BK-1"),
            email("c", booking="BK-1", oc="OC-2"),
            email("d", oc="OC-2"),
        ])
        assert got == [{"a", "b", "c", "d"}]


class TestResemblanceIsNotAnEdge:
    def test_same_customer_and_lane_do_not_group(self):
        """email_468 and email_502: both Roxcel to Ashdod, one 40'HC, and
        different shipments. Only the references decide."""
        a = email("email_468", oc="5ALT-45057")
        b = email("email_502", oc="5RSG-63369")
        a["shipment"] = b["shipment"] = {
            "consignee": "ROXCEL TRADING GMBH",
            "port_of_loading": "SINGAPORE (SGSIN)",
            "port_of_discharge": "ASHDOD, ISRAEL (ILASH)",
            "container_count": "1 X 40'HC",
        }
        assert folders([a, b]) == [{"email_468"}, {"email_502"}]


class TestTheCorpusItself:
    def test_every_component_in_the_bundle_has_one_email(self, results):
        """If this ever fails, the corpus grew a thread and the UI should be
        showing it - which is worth knowing loudly rather than silently."""
        emails = [{"email_id": r.email_id, "oc_number": r.oc_number,
                   "booking_ref": r.booking_ref} for r in results.values()]
        sizes = {len(f) for f in folders(emails)}
        assert sizes == {1}, f"a component grew: sizes {sorted(sizes)}"
