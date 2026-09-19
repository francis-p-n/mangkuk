import pytest

from conftest import DATA_DIR

from sdoc.documents import DocType, Document, extract, identify
from sdoc.mailsource import BundleMailSource


class TestIdentify:
    @pytest.mark.parametrize("head,expected", [
        ("SHIPPING INSTRUCTION\n====\nShipper: X", DocType.SHIPPING_INSTRUCTION),
        ("BILL OF LADING (DRAFT)\n====\nSHIPPER: X", DocType.BILL_OF_LADING),
        ("ACME PTE LTD\nBL INSTRUCTION: 3154303911\nSHIPPER: X", DocType.SHIPPING_INSTRUCTION),
        ("ACME PTE LTD\nBILL OF LADING: 3154303911\nSHIPPER: X", DocType.BILL_OF_LADING),
        ("PACKING LIST\n====\nGross: 1", DocType.PACKING_LIST),
        ("CERTIFICATE OF ORIGIN\n====", DocType.CERTIFICATE_OF_ORIGIN),
        ("COMMERCIAL INVOICE\n====", DocType.COMMERCIAL_INVOICE),
        ("SOME OTHER PAPER\n====", DocType.UNKNOWN),
    ])
    def test_title_block_decides(self, head, expected):
        assert identify(head) == expected

    def test_only_the_title_block_is_considered(self):
        body = "SHIPPING INSTRUCTION\n" + "\n".join(f"Field {i}: v" for i in range(80))
        body += "\nBILL OF LADING NOTES: ignore me"
        assert identify(body) == DocType.SHIPPING_INSTRUCTION


class TestRoleGuard:
    def test_role_comes_from_the_filename(self):
        assert Document(path="attachments/email_1_SI.txt", role="SI", fmt=".txt").expected_type \
            == DocType.SHIPPING_INSTRUCTION

    def test_decoy_is_caught(self):
        doc = Document(path="p", role="BL", fmt=".txt", doc_type=DocType.PACKING_LIST, ok=True)
        assert not doc.type_matches_role


class TestExtractRealAttachments:
    src = BundleMailSource(DATA_DIR)

    def test_text_attachment(self):
        doc = extract(self.src, "attachments/email_001_SI.txt")
        assert doc.ok and doc.doc_type == DocType.SHIPPING_INSTRUCTION and doc.type_matches_role

    def test_spreadsheet_attachment(self):
        doc = extract(self.src, "attachments/email_005_SI.xlsx")
        assert doc.ok and doc.doc_type == DocType.SHIPPING_INSTRUCTION

    def test_word_attachment(self):
        doc = extract(self.src, "attachments/email_055_BL.docx")
        assert doc.ok and doc.doc_type == DocType.BILL_OF_LADING

    def test_text_bearing_pdf_is_read(self):
        doc = extract(self.src, "attachments/email_059_SI.pdf")
        assert doc.ok and "APRIL FINE PAPER TRADING" in doc.text

    def test_pdf_instruction_is_not_mistaken_for_a_bill_of_lading(self):
        # The PDF SI is titled "BILL OF LADING INSTRUCTION".
        doc = extract(self.src, "attachments/email_059_SI.pdf")
        assert doc.doc_type == DocType.SHIPPING_INSTRUCTION and doc.type_matches_role

    def test_image_only_pdf_is_declared_unreadable_rather_than_guessed(self):
        doc = extract(self.src, "attachments/email_513_SI.pdf")
        assert not doc.ok and doc.error == "unreadable"

    def test_missing_file_does_not_raise(self):
        doc = extract(self.src, "attachments/does_not_exist_SI.txt")
        assert not doc.ok and doc.error == "unreadable"
