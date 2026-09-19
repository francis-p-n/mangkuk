import pytest

from sdoc.fields import extract_fields, label_to_field, normalize_label

SI = """SHIPPING INSTRUCTION
========================================

Shipper/Exporter: APRIL FAR EAST (M) SDN BHD
  TOWER 2, AVENUE 5, LEVEL 6; BANGSAR SOUTH CITY
CONSIGNEE: MOORIM SP CO., LTD
Notify Party/Intermediate Consignee: UAB NOVAKOPA
Port of Loading: PORT KLANG (WESTPORT), MALAYSIA (MYPKG)
Discharge Port: CALLAO, PERU (PECLL)
No. of Containers or Packages: 1 x 40'HC
Gross Weight毛重(KGS): 21,577 KG
NET WEIGHT: _______ MTS
Kinds of Packages; Description of Goods: PAPERONE DIGITAL COPIER PAPER
Booking Ref: MSDUL0942518196
"""


class TestLabelAlignment:
    @pytest.mark.parametrize("label,expected", [
        ("Shipper/Exporter", "shipper"),
        ("Shipper (Principal or Seller)", "shipper"),
        ("CONSIGNEE", "consignee"),
        ("Consignee (Non-Negotiable)", "consignee"),
        ("To the Order of", "consignee"),
        ("NOTIFY PARTY", "notify_party"),
        ("Port of Loading (POL)", "port_of_loading"),
        ("Load Port", "port_of_loading"),
        ("POL", "port_of_loading"),
        ("POD", "port_of_discharge"),
        ("Discharge Port", "port_of_discharge"),
        ("Total Containers", "container_count"),
        ("No. of Containers or Packages", "container_count"),
        ("Gross Wt (kgs)", "gross_weight_kg"),
    ])
    def test_known_aliases(self, label, expected):
        assert label_to_field(label) == expected

    def test_notify_wins_over_consignee_in_a_compound_label(self):
        # 'Notify Party/Intermediate Consignee' contains both words. Order decides.
        assert label_to_field("Notify Party/Intermediate Consignee") == "notify_party"

    def test_cjk_characters_in_a_label_are_stripped(self):
        assert normalize_label("Gross Weight毛重(KGS)") == "gross weight kgs"
        assert label_to_field("Gross Weight毛重(KGS)") == "gross_weight_kg"

    @pytest.mark.parametrize("label", [
        "NET WEIGHT",
        "Kinds of Packages; Description of Goods",
        "Export Carrier (vessel, voyage)",
        "Booking Ref",
        "HS Code",
        "Freight",
    ])
    def test_lookalike_labels_are_not_captured(self, label):
        assert label_to_field(label) is None


class TestExtraction:
    def test_extracts_all_seven(self):
        fs = extract_fields(SI)
        assert not fs.missing

    def test_values_and_evidence(self):
        fs = extract_fields(SI)
        shipper = fs.get("shipper")
        assert shipper.value == "APRIL FAR EAST (M) SDN BHD"
        assert shipper.label == "Shipper/Exporter"
        assert shipper.line_no == 4
        assert "TOWER 2" in shipper.detail

    def test_net_weight_does_not_overwrite_gross(self):
        assert extract_fields(SI).get("gross_weight_kg").value == "21,577 KG"

    def test_blank_value_is_treated_as_absent(self):
        fs = extract_fields("SHIPPING INSTRUCTION\n\nSHIPPER: \nCONSIGNEE: UAB NOVAKOPA\n")
        assert "shipper" in fs.missing
        assert fs.get("consignee").value == "UAB NOVAKOPA"

    def test_first_occurrence_wins(self):
        fs = extract_fields("Shipper: FIRST CORP\nShipper: SECOND CORP\n")
        assert fs.get("shipper").value == "FIRST CORP"

    def test_flattened_spreadsheet_row_splits_name_from_address(self):
        fs = extract_fields("SHIPPER: ACME PTE LTD | 80 RAFFLES PLACE; SINGAPORE")
        assert fs.get("shipper").value == "ACME PTE LTD"
        assert fs.get("shipper").detail == "80 RAFFLES PLACE; SINGAPORE"
