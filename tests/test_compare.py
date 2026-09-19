from sdoc.compare import compare_documents, compare_fieldsets
from sdoc.documents import DocType, Document
from sdoc.fields import extract_fields

SI = """SHIPPING INSTRUCTION

Shipper: APRIL FAR EAST (M) SDN BHD
Consignee (Non-Negotiable): EAST BRIGHT FZ-LLC
Notify: EAST BRIGHT FZ-LLC
Port of Loading: PORT KLANG, MALAYSIA (MYPKG)
Discharge Port: CALLAO, PERU (PECLL)
Total Containers: 6 x 40'HC
Gross Wt (kgs): 131,058 KG
"""

BL_CLEAN = """BILL OF LADING (DRAFT)

SHIPPER: APRIL FAR EAST (M) SDN BHD
CONSIGNEE: EAST BRIGHT FZ-LLC
Notify Party: EAST BRIGHT FZ-LLC
POL: PORT KLANG, MALAYSIA (MYPKG)
POD: CALLAO, PERU (PECLL)
Container Count: 6 x 40'HC
Gross Weight(KG): 131,058 KG
"""


def _doc(role, text, doc_type, ok=True, error=None):
    return Document(path=f"a_{role}.txt", role=role, fmt=".txt", text=text,
                    doc_type=doc_type, ok=ok, error=error)


def si_doc(text=SI):
    return _doc("SI", text, DocType.SHIPPING_INSTRUCTION)


def bl_doc(text=BL_CLEAN):
    return _doc("BL", text, DocType.BILL_OF_LADING)


class TestHappyPath:
    def test_all_seven_match_across_different_labels(self):
        v = compare_documents(si_doc(), bl_doc())
        assert v.status == "OK"
        assert v.defect_fields == [] and v.has_defect is False
        assert len(v.comparisons) == 7

    def test_every_comparison_carries_both_labels_as_evidence(self):
        v = compare_documents(si_doc(), bl_doc())
        pol = next(c for c in v.comparisons if c.field == "port_of_loading")
        assert pol.si_label == "Port of Loading" and pol.bl_label == "POL"
        assert pol.si_line > 0 and pol.bl_line > 0


class TestDefects:
    def test_swapped_party_is_flagged_on_both_fields(self):
        bl = BL_CLEAN.replace("EAST BRIGHT FZ-LLC", "UAB NOVAKOPA")
        v = compare_documents(si_doc(), bl_doc(bl))
        assert v.status == "MISMATCH" and v.has_defect
        assert set(v.defect_fields) == {"consignee", "notify_party"}

    def test_container_count_defect(self):
        v = compare_documents(si_doc(), bl_doc(BL_CLEAN.replace("6 x 40'HC", "4 x 40'HC")))
        assert v.defect_fields == ["container_count"]

    def test_defect_fields_are_reported_in_canonical_order(self):
        bl = BL_CLEAN.replace("6 x 40'HC", "4 x 40'HC").replace("APRIL FAR EAST (M) SDN BHD", "OTHER CORP")
        v = compare_documents(si_doc(), bl_doc(bl))
        assert v.defect_fields == ["shipper", "container_count"]


class TestBlockers:
    def test_missing_attachment(self):
        v = compare_documents(si_doc(), None)
        assert v.status == "NEEDS_REVIEW" and v.review_reason == "missing_attachment"

    def test_unreadable_outranks_doc_type(self):
        bad = _doc("BL", "", DocType.UNKNOWN, ok=False, error="unreadable")
        v = compare_documents(si_doc(), bad)
        assert v.review_reason == "unreadable"

    def test_wrong_doc_type_names_what_it_actually_is(self):
        decoy = _doc("BL", "PACKING LIST\n", DocType.PACKING_LIST)
        v = compare_documents(si_doc(), decoy)
        assert v.review_reason == "wrong_doc_type" and "packing list" in v.note

    def test_missing_value_when_nothing_conflicts(self):
        si = SI.replace("Shipper: APRIL FAR EAST (M) SDN BHD", "Shipper: ")
        v = compare_documents(si_doc(si), bl_doc())
        assert v.status == "NEEDS_REVIEW" and v.review_reason == "missing_value"
        assert "shipper" in v.note


class TestPrecedence:
    def test_a_real_defect_outranks_an_unreadable_field(self):
        # An unreadable shipper must not bury a genuine container mismatch.
        si = SI.replace("Shipper: APRIL FAR EAST (M) SDN BHD", "Shipper: ")
        bl = BL_CLEAN.replace("6 x 40'HC", "9 x 40'HC")
        v = compare_fieldsets(extract_fields(si), extract_fields(bl))
        assert v.status == "MISMATCH" and v.defect_fields == ["container_count"]
