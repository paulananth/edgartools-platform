"""The name, jurisdiction and postal tests the SEC-to-GLEIF matching rule reads.

Company mastering ticket 08. Each case is a real pair from the development
data (`.scratch/company-mastering/research/08-draft-rule.md`).
"""

import pytest

from edgar_warehouse.mdm.clean.names import (
    edgar_jurisdiction,
    jurisdictions_agree,
    jurisdictions_conflict,
    legal_form_key,
    postal_codes_agree,
    sec_legal_form_key,
)
from edgar_warehouse.mdm.clean.primitives import NORMALIZERS


class TestTheLegalFormIsKept:
    @pytest.mark.parametrize(
        ("sec", "gleif"),
        [
            ("VISTEON CORP", "VISTEON CORPORATION"),
            ("COCA COLA CO", "THE COCA-COLA COMPANY"),
            ("APPLE INC", "Apple Inc."),
            ("ASML HOLDING NV", "ASML Holding N.V."),
            ("Shell plc", "Shell plc"),
            ("MCCORMICK & CO INC", "McCormick & Company, Incorporated"),
            ("ACME L.L.C.", "ACME LLC"),
        ],
    )
    def test_one_entity_spelled_two_ways_has_one_key(self, sec, gleif):
        assert sec_legal_form_key(sec) == legal_form_key(gleif)

    @pytest.mark.parametrize(
        ("sec", "gleif"),
        [
            ("Wayfair Inc.", "WAYFAIR LLC"),
            ("ADT Inc.", "ADT LLC"),
            ("COUSINS PROPERTIES INC", "COUSINS PROPERTIES LP"),
            ("REGENCY CENTERS LP", "REGENCY CENTERS CORPORATION"),
            ("Drilling Tools International Corp", "Drilling Tools International, Inc."),
        ],
    )
    def test_a_parent_and_its_subsidiary_keep_two_keys(self, sec, gleif):
        assert sec_legal_form_key(sec) != legal_form_key(gleif)

    def test_sec_drops_its_state_tag_and_gleif_keeps_its_name(self):
        assert (
            sec_legal_form_key("BERKSHIRE HATHAWAY INC /DE/")
            == "BERKSHIRE HATHAWAY INC"
        )
        # A GLEIF legal name is never a SEC conformed name, so a slash stays text.
        assert legal_form_key("X /DE/") == "X DE"

    def test_a_blank_name_has_no_key(self):
        assert sec_legal_form_key(None) == ""
        assert legal_form_key("  ") == ""

    def test_both_are_registered_versioned_normalizers(self):
        assert NORMALIZERS["normalize_text@legal-form-kept-v1"] is legal_form_key
        assert (
            NORMALIZERS["normalize_text@sec-legal-form-kept-v1"] is sec_legal_form_key
        )


class TestEdgarCodesBecomeIso:
    @pytest.mark.parametrize(
        ("code", "iso"),
        [
            ("DE", "US-DE"),
            ("ca", "US-CA"),
            ("P7", "NL"),
            ("X0", "GB"),
            ("A6", "CA-ON"),
            ("E9", "KY"),
            ("Z4", "CA"),
            ("X1", "US"),
        ],
    )
    def test_a_known_code(self, code, iso):
        assert edgar_jurisdiction(code) == iso

    @pytest.mark.parametrize("code", [None, "", "XX", "I9", "??"])
    def test_an_unknown_code_is_none(self, code):
        assert edgar_jurisdiction(code) is None


class TestJurisdictionsAgree:
    @pytest.mark.parametrize(
        ("sec", "gleif"),
        [
            ("US-DE", "US-DE"),
            ("NL", "NL"),
            ("GB", "GB-ENG"),  # a country-only side agrees with its subdivision
            ("CA-ON", "CA"),
            ("US-PR", "PR"),  # SEC codes Puerto Rico as a state, GLEIF as a country
        ],
    )
    def test_agree(self, sec, gleif):
        assert jurisdictions_agree(sec, gleif)

    @pytest.mark.parametrize(
        ("sec", "gleif"),
        [
            ("US-DE", "US-NV"),
            ("US-DE", "US"),  # a US record must name its state
            ("US", "US-DE"),
            ("CA-ON", "CA-BC"),
            ("KY", "US-DE"),
            (None, "US-DE"),
            ("US-DE", None),
        ],
    )
    def test_disagree(self, sec, gleif):
        assert not jurisdictions_agree(sec, gleif)


class TestPostalCodesAgree:
    def test_same_code_same_country(self):
        assert postal_codes_agree("95014", "US", "95014-2083", "US")
        assert postal_codes_agree("SE1 7NA", "GB", "SE17NA", "GB")

    def test_a_different_country_never_agrees(self):
        assert not postal_codes_agree("95014", "US", "95014", "DE")

    def test_sec_keeps_only_the_digits_of_a_dutch_code(self):
        assert postal_codes_agree("5504", "NL", "5504 DR", "NL")

    def test_only_the_dutch_shape_agrees_on_a_prefix(self):
        assert not postal_codes_agree("5504", "BE", "5504DR", "BE")
        assert not postal_codes_agree("1234", "NL", "12345", "NL")
        assert not postal_codes_agree("SE1", "GB", "SE17NA", "GB")

    def test_a_blank_code_never_agrees(self):
        assert not postal_codes_agree("", "US", "", "US")
        assert not postal_codes_agree(None, "US", "95014", "US")


class TestJurisdictionsConflict:
    """Ticket 08: the postal step's veto, from the Name-and-postcode rule's misses."""

    @pytest.mark.parametrize(
        ("sec", "gleif"),
        [
            ("US-NV", "US-OK"),  # AAON: a Nevada parent, its Oklahoma subsidiary
            ("US-VA", "US-IL"),
            ("CA-BC", "CA-ON"),
            ("KY", "CA-ON"),
            ("MU", "KY"),
        ],
    )
    def test_two_definite_places_conflict(self, sec, gleif):
        assert jurisdictions_conflict(sec, gleif, sec_business_country="US")

    @pytest.mark.parametrize(
        ("sec", "gleif"),
        [
            ("US-DE", "US-DE"),  # they agree
            (None, "US-DE"),  # SEC names no place
            ("US-DE", None),
            ("US", "US-DE"),  # a country-only side is no conflict in that country
            ("US-DE", "US"),
            ("CA", "CA-ON"),
        ],
    )
    def test_no_conflict(self, sec, gleif):
        assert not jurisdictions_conflict(sec, gleif, sec_business_country="US")

    def test_a_us_state_both_other_sources_contradict_is_set_aside(self):
        # Shell: SEC's state of incorporation reads "DC", but SEC's own business
        # address and GLEIF's jurisdiction both put Shell in Britain.
        assert not jurisdictions_conflict("US-DC", "GB", sec_business_country="GB")
        assert jurisdictions_conflict("US-DC", "GB", sec_business_country="US")
        assert jurisdictions_conflict("US-DC", "GB", sec_business_country=None)
