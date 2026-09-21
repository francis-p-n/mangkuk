"""Emails are vertices, references are edges, a shipment is a component.

These run against the grouping that ships - `web/lib/graph.ts`, through
`tools/group_cli.mjs` - rather than against a copy of it. The copy this file
used to carry was the whole problem: deleting bridging from the real
`componentsOf` left every test here green and the typecheck clean, and the
copy had never learned that a B/L number is an edge either.

The rules themselves are unit-tested next to the code, in
`web/lib/graph.test.ts` (`npm test --prefix web`). What is asserted here is
the part that needs the pipeline: that the real corpus files the way it is
claimed to, and that the constructed thread folds into one shipment with the
right verdict on it.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from conftest import DATA_DIR, ROOT
from sdoc.mailsource import BundleMailSource
from sdoc.pipeline import run

CLI = ROOT / "tools" / "group_cli.mjs"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node runs the grouping; install Node 22.6+ to check it",
)


def rows_of(results) -> list[dict]:
    """A result as the web app's list query sees it."""
    return [
        {
            "email_id": r.email_id,
            "category": r.category,
            "status": r.status,
            "severity": r.severity,
            "oc_number": r.oc_number,
            "booking_ref": r.booking_ref,
            "shipment": {"bl_number": (r.shipment or {}).get("bl_number")},
        }
        for r in results
    ]


def group(rows: list[dict]) -> list[dict]:
    """Run the shipped grouping over these rows and return the files."""
    out = subprocess.run(
        ["node", str(CLI)],
        input=json.dumps(rows),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=120,
    )
    if out.returncode != 0:
        pytest.fail(f"the grouping would not run:\n{out.stderr.strip()[-800:]}")
    return json.loads(out.stdout)["files"]


@pytest.fixture(scope="module")
def bundle():
    return list(run(BundleMailSource(DATA_DIR)))


@pytest.fixture(scope="module")
def thread():
    src = DATA_DIR / "thread-demo"
    if not (src / "inbox").exists():
        pytest.skip("run tools/thread_demo.py to build the fixture")
    return list(run(BundleMailSource(src)))


class TestTheCorpusItself:
    """The corpus cannot exercise the grouping, and that is worth pinning.

    Every reference in it belongs to exactly one email - 388 OC numbers across
    388 emails, 222 bookings across 222 - so all 520 components have size one.
    """

    def test_every_file_in_the_bundle_holds_one_email(self, bundle):
        files = group(rows_of(bundle))
        sizes = {len(f["emails"]) for f in files}
        assert sizes == {1}, f"a file grew: sizes {sorted(sizes)}"
        assert len(files) == len(bundle)

    def test_no_email_is_lost_or_duplicated_by_the_grouping(self, bundle):
        filed = [eid for f in group(rows_of(bundle)) for eid in f["emails"]]
        assert sorted(filed) == sorted(r.email_id for r in bundle)

    def test_only_document_checks_carry_a_verdict(self, bundle):
        """391 emails are stored as OK because nothing was asked of them."""
        by_id = {r.email_id: r for r in bundle}
        for f in group(rows_of(bundle)):
            head = by_id[f["emails"][0]]
            if head.category == "BL_COMPARISON":
                assert f["checked"] and f["status"] == head.status
            else:
                assert not f["checked"] and f["status"] is None

    def test_resemblance_does_not_file_two_shipments_together(self, bundle):
        """email_468 and email_502: both Roxcel to Ashdod, one 40'HC."""
        files = group(rows_of(bundle))
        homes = [f for f in files
                 if {"email_468", "email_502"} & set(f["emails"])]
        assert len(homes) == 2


class TestTheConstructedThread:
    """The fixture that makes the filing demonstrable.

    Built by tools/thread_demo.py and kept out of the scored bundle. These
    assert what the corpus cannot: one container's paperwork from booking to
    arrival, filed together, with a draft that is wrong twice before it is
    right.
    """

    def test_the_whole_correspondence_is_one_shipment(self, thread):
        files = group(rows_of(thread))
        assert len(files) == 1
        assert len(files[0]["emails"]) == 12 == len(thread)

    def test_it_files_under_the_reference_a_desk_would_quote(self, thread):
        assert group(rows_of(thread))[0]["reference"] == "7QTX-40118"

    def test_mail_that_is_not_a_document_check_files_here_too(self, thread):
        """A booking confirmation, an invoice and an arrival notice belong in
        the shipment's file as much as the drafts do."""
        kinds = {r.category for r in thread}
        assert {"BL_COMPARISON", "GENERAL", "INVOICE_QUERY"} <= kinds

    def test_the_first_draft_is_wrong_in_two_places(self, thread):
        first = {r.email_id: r for r in thread}["email_9003"]
        assert first.status == "MISMATCH"
        assert sorted(first.defect_fields) == ["consignee", "gross_weight_kg"]

    def test_the_first_correction_fixes_only_one_of_them(self, thread):
        """The shape that matters. A demo where the first correction lands
        says nothing about what a desk spends its week on."""
        second = {r.email_id: r for r in thread}["email_9005"]
        assert second.status == "MISMATCH"
        assert second.defect_fields == ["gross_weight_kg"]

    def test_the_second_correction_closes_it(self, thread):
        assert {r.email_id: r for r in thread}["email_9008"].status == "OK"

    def test_the_file_therefore_reads_as_corrected(self, thread):
        """The whole point of filing the thread together. This is what was
        broken: the fold dropped clean checks before choosing the deciding
        email, so the file could only ever end on a failure."""
        f = group(rows_of(thread))[0]
        assert f["status"] == "OK"
        assert f["resolved"] is True
        assert f["decisive"] == "email_9008"

    def test_the_arrival_notice_does_not_decide_the_file(self, thread):
        """It is the last email in the thread and it was never compared."""
        assert group(rows_of(thread))[0]["decisive"] != "email_9012"

    def test_the_release_notice_files_on_its_booking_alone(self, thread):
        last = {r.email_id: r for r in thread}["email_9010"]
        assert last.oc_number is None
        assert last.booking_ref == "MEDUTH550281"

    def test_the_bl_number_is_read_off_the_draft(self, thread):
        """Printed on the bill of lading and never on the instruction, so it
        is only found by reading both documents."""
        by_id = {r.email_id: r for r in thread}
        assert by_id["email_9003"].shipment.get("bl_number") == "MEDUTH550281X"
        assert by_id["email_9008"].shipment.get("bl_number") == "MEDUTH550281X"


class TestTheGraphIsTheOneThatShips:
    def test_the_cli_and_the_unit_tests_read_the_same_module(self):
        """A guard against this file quietly growing its own copy again."""
        source = CLI.read_text(encoding="utf-8")
        assert 'from "../web/lib/graph.ts"' in source
