import pytest

from sdoc.classify import classify, clean_body

BANNER = "WARNING: This email originated outside of our organisation. As a security measure, do not click links.\n\n"
ATT = ["attachments/email_001_SI.txt", "attachments/email_001_BL.txt"]


def cat(subject="", body="", domain="aprilasia.com", attachments=None):
    return classify(subject, body, domain, attachments or []).category


class TestSpam:
    @pytest.mark.parametrize("domain", [
        "webmail-verify.co", "prize-claims.info", "crypto-invest.net", "logistics-deals.biz",
    ])
    def test_known_bad_domains(self, domain):
        assert cat(subject="Draft BL amend", domain=domain) == "SPAM"

    def test_phrase_from_a_plausible_domain(self):
        assert cat(body="CONGRATULATIONS!!! Your email address has been selected") == "SPAM"

    def test_spam_outranks_shipping_vocabulary(self):
        assert cat(subject="TO CONFIRM DOCS _ 5RSG-00133", body="You have won a brand new iPhone!",
                   domain="prize-claims.info") == "SPAM"


class TestComparison:
    def test_attachments_decide(self):
        assert cat(subject="REQUEST BL DRAFT _ PO 26067", body="Attached are the SI and draft BL",
                   attachments=ATT) == "BL_COMPARISON"

    def test_phrase_without_attachments_still_counts(self):
        assert cat(body="Pls assist to check the draft BL against the SI for PO") == "BL_COMPARISON"

    def test_chasing_a_draft_is_not_a_comparison(self):
        # Nothing has arrived yet, so there is nothing to compare.
        assert cat(subject="RE_ TO CONFIRM DOCS _ 5AAT-03056",
                   body="Please assist to send the draft BL for SIN832764835 for checking asap.") == "GENERAL"

    def test_security_banner_does_not_change_the_verdict(self):
        body = BANNER + "Attached are the SI and draft BL for OC 5RSG-00133."
        assert cat(body=body, attachments=ATT) == "BL_COMPARISON"


class TestOtherCategories:
    def test_si_request_from_body(self):
        assert cat(subject="CUST SI _ MEA _ 5RCY-52735",
                   body="Please find Shipping instruction for 5RCY-52735.") == "SI_REQUEST"

    def test_si_request_from_subject_only(self):
        assert cat(subject="SI NEEDED_ 5RCY-63982 _ 3S PAPER PRODUCTS") == "SI_REQUEST"

    def test_invoice_query(self):
        assert cat(subject="Total Freight - INDIA - 5ALT-38425",
                   body="Query on invoice 5250071354: is the THC / local charge included?") == "INVOICE_QUERY"

    def test_operational_update_is_general(self):
        assert cat(subject="15_01_2026 - UPDATE SUMMARY LE HAVRE",
                   body="Please find attached the list of outstanding BL (BDP SG).") == "GENERAL"


class TestCleanBody:
    def test_banner_removed(self):
        assert "WARNING" not in clean_body(BANNER + "Real content here.")

    def test_quoted_reply_dropped(self):
        body = "My question.\n\n______________________________\nFrom: someone\nOld thread text"
        assert "Old thread" not in clean_body(body)
        assert "My question." in clean_body(body)
