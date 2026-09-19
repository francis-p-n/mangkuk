from sdoc.normalize import (
    Port, norm_party, parse_containers, parse_port, parse_weight, values_agree,
)


class TestParty:
    def test_legal_suffix_is_noise(self):
        assert norm_party("MOORIM SP CO., LTD") == norm_party("Moorim SP Co Ltd")

    def test_stacked_suffixes_all_stripped(self):
        assert norm_party("VITAL SOLUTIONS PTE. LTD.") == "vital solutions"

    def test_different_companies_stay_different(self):
        assert norm_party("EAST BRIGHT FZ-LLC") != norm_party("UAB NOVAKOPA")

    def test_agreement_ignores_punctuation_and_case(self):
        assert values_agree("consignee", "ROXCEL TRADING GMBH", "Roxcel Trading GmbH") is True

    def test_blank_value_is_undecidable_not_a_defect(self):
        assert values_agree("shipper", "", "APRIL FINE PAPER TRADING") is None


class TestPort:
    def test_splits_city_country_locode(self):
        p = parse_port("TUTICORIN, INDIA (KEMBA)")
        assert (p.city, p.country, p.locode) == ("tuticorin", "india", "KEMBA")

    def test_same_locode_different_city_is_a_conflict(self):
        # The trap in email_013: the code agrees, the port does not.
        assert values_agree(
            "port_of_discharge", "MOMBASA, KENYA (KEMBA)", "TUTICORIN, INDIA (KEMBA)"
        ) is False

    def test_same_city_different_locode_is_a_conflict(self):
        assert values_agree(
            "port_of_discharge", "FREMANTLE, AUSTRALIA (AUFRE)", "FREMANTLE, AUSTRALIA (AUBNE)"
        ) is False

    def test_missing_locode_on_one_side_is_not_a_conflict(self):
        assert values_agree("port_of_loading", "SINGAPORE", "SINGAPORE (SGSIN)") is True

    def test_conflict_is_symmetric(self):
        a, b = Port("koper", "slovenia", "SIKOP"), Port("busan", "south korea", "SIKOP")
        assert a.conflicts_with(b) and b.conflicts_with(a)


class TestContainers:
    def test_parses_count_size_kind(self):
        c = parse_containers("6 x 40'HC")
        assert (c.count, c.size, c.kind) == (6, "40", "HC")

    def test_spacing_and_quote_variants_agree(self):
        assert values_agree("container_count", "6 x 40'HC", "6 X 40 HC") is True

    def test_count_difference_is_a_defect(self):
        assert values_agree("container_count", "3 x 40'HC", "4 x 40'HC") is False

    def test_kind_difference_is_a_defect(self):
        assert values_agree("container_count", "6 x 20'GP", "6 x 20'FCL") is False

    def test_bare_number_still_parses(self):
        assert parse_containers("4").count == 4


class TestWeight:
    def test_thousands_separator_and_unit_are_noise(self):
        assert values_agree("gross_weight_kg", "21,577 KG", "21577") is True

    def test_real_difference_is_a_defect(self):
        assert values_agree("gross_weight_kg", "21,114 KG", "23,114 KG") is False

    def test_na_is_undecidable(self):
        assert parse_weight("N/A") is None
        assert values_agree("gross_weight_kg", "N/A", "235,550 KG") is None
