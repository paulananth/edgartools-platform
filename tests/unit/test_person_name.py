"""Tests for edgar_warehouse.domain.policy.person_name (Person Consumer Contract ticket 25).

The three defects research 21 measured in research 17's name normalizer, each
pinned by the real names it failed on, plus the behaviour that must not move.
"""
from __future__ import annotations

import pytest

from edgar_warehouse.domain.policy.person_name import (
    GENERATIONAL_SUFFIXES,
    NORMALIZER_VERSION,
    is_person_name_candidate,
    parse_conformed,
    parse_western,
)


def test_version_is_declared():
    assert NORMALIZER_VERSION == "person-name@v2"


class TestMultiWordSurname:
    """Defect 1: a surname particle was read as the given name."""

    def test_zegna_brothers_no_longer_share_a_key(self):
        # research 21 F6/F7b: both parsed to ZEGNA|DI|M -- the fixed key's only
        # false merge against Form 3/4/5's 11 same-issuer homonym CIK pairs.
        edoardo = parse_conformed("Zegna di Monte Rubello Edoardo")
        angelo = parse_conformed("Zegna di Monte Rubello Angelo")
        assert edoardo.first != "DI" and angelo.first != "DI"
        assert edoardo.key_mi != angelo.key_mi

    @pytest.mark.parametrize(
        ("raw", "last", "first", "middle"),
        [
            ("Bodin de Moraes Pedro Luiz", "BODIN DE MORAES", "PEDRO", ("LUIZ",)),
            ("Gomide de Faria Mariano", "GOMIDE DE FARIA", "MARIANO", ()),
            ("Foufopoulos - De Ridder Lucrece", "FOUFOPOULOS DE RIDDER", "LUCRECE", ()),
            ("DE LA HOYA OSCAR", "DE LA HOYA", "OSCAR", ()),
            ("VAN DER BERG JAN P", "VAN DER BERG", "JAN", ("P",)),
        ],
    )
    def test_conformed_particles_join_the_surname(self, raw, last, first, middle):
        p = parse_conformed(raw)
        assert (p.last, p.first, p.middle) == (last, first, middle)
        assert p.shape

    @pytest.mark.parametrize(
        ("raw", "last", "first", "middle"),
        [
            ("Ludwig van Beethoven", "VAN BEETHOVEN", "LUDWIG", ()),
            ("Maria de la Cruz", "DE LA CRUZ", "MARIA", ()),
            ("La Vonda Williams", "WILLIAMS", "LA VONDA", ()),
            ("Mr. Van Vleet", "VAN VLEET", "", ()),
            ("Del Pozzo", "DEL POZZO", "", ()),
        ],
    )
    def test_western_particles_join_the_surname_or_given_name(self, raw, last, first, middle):
        p = parse_western(raw)
        assert (p.last, p.first, p.middle) == (last, first, middle)
        assert p.shape == bool(first)

    def test_a_particle_is_never_the_given_name(self):
        for raw in ("Zegna di Monte Rubello Edoardo", "Bodin de Moraes Pedro Luiz", "DE LA HOYA OSCAR"):
            assert parse_conformed(raw).first not in {"DI", "DE", "LA", "VAN", "VON", "DA", "LE", "DOS"}
        for raw in ("La Vonda Williams", "Maria de la Cruz", "Ludwig van Beethoven"):
            assert parse_western(raw).first not in {"DI", "DE", "LA", "VAN", "VON", "DA", "LE", "DOS"}

    @pytest.mark.parametrize(
        ("conformed", "western", "first"),
        [
            ("Williams La Vonda", "La Vonda Williams", "LA VONDA"),
            ("EISNOR DI-ANN", "Di-Ann Eisnor", "DI ANN"),
            ("Hu Da-Wai", "Da-Wai Hu", "DA WAI"),
        ],
    )
    def test_a_particle_led_given_name_reads_the_same_in_both_forms(self, conformed, western, first):
        # research 21's labelled pair "La Vonda Williams" / "Williams La Vonda" is `same`;
        # the two forms must produce one key.
        c, w = parse_conformed(conformed), parse_western(western)
        assert c.first == w.first == first
        assert c.key_mi == w.key_mi

    @pytest.mark.parametrize(
        ("conformed", "western", "last", "first", "middle"),
        [
            # Standalone Indian / Chinese / Vietnamese surnames that are also on the
            # particle list: never a leading particle (review B1 -- v2's first cut
            # read "DAS MANUVIR" as a surname with no given name).
            ("DAS MANUVIR", "Manuvir Das", "DAS", "MANUVIR", ()),
            ("DU WEI", "Wei Du", "DU", "WEI", ()),
            ("LE TUAN", "Tuan Le", "LE", "TUAN", ()),
            ("DU ZHI QIANG", "Zhi Qiang Du", "DU", "ZHI", ("QIANG",)),
            ("LE TRUC THANH", "Truc Thanh Le", "LE", "TRUC", ("THANH",)),
            ("DO CUONG V", "Cuong V. Do", "DO", "CUONG", ("V",)),
        ],
    )
    def test_standalone_surnames_on_the_particle_list(self, conformed, western, last, first, middle):
        c, w = parse_conformed(conformed), parse_western(western)
        assert (c.last, c.first, c.middle) == (last, first, middle)
        assert (w.last, w.first, w.middle) == (last, first, middle)
        assert c.key_mi == w.key_mi
        assert c.shape and w.shape

    def test_do_is_a_particle_mid_name_and_never_a_credential(self):
        # review S1: DO sat on both lists, so the particle entry was dead and the
        # Vietnamese surname Do was stripped as a credential.
        assert parse_conformed("SANTOS DO CARMO MARIA").last == "SANTOS DO CARMO"
        assert "DO" not in parse_western("Anh Do").suffixes
        assert parse_western("Anh Do").last == "DO"

    def test_a_leading_particle_run_leaves_a_given_name(self):
        p = parse_conformed("DE SILVA")
        assert (p.last, p.first) == ("DE", "SILVA")

    def test_a_trailing_particle_like_token_with_nothing_after_it_stays_a_given_name(self):
        # "SMITH DEL": no token remains to be the given name, so DEL is it.
        p = parse_conformed("SMITH DEL")
        assert (p.last, p.first) == ("SMITH", "DEL")

    def test_ordinary_names_are_unchanged(self):
        p = parse_conformed("COOK TIMOTHY D")
        assert (p.last, p.first, p.middle, p.key_mi) == ("COOK", "TIMOTHY", ("D",), "COOK|TIMOTHY|D")
        w = parse_western("Timothy D. Cook")
        assert (w.last, w.first, w.middle, w.key_mi) == ("COOK", "TIMOTHY", ("D",), "COOK|TIMOTHY|D")


class TestVIsNotAGenerationalSuffix:
    """Defect 2: V was a suffix token, so a middle initial V was discarded."""

    def test_generational_set_is_ticket_20s_list(self):
        assert GENERATIONAL_SUFFIXES == frozenset({"JR", "SR", "II", "III", "IV"})

    @pytest.mark.parametrize("raw", ["CRAWFORD MATTHEW V", "Bergh Charles V", "Caldwell Nick V."])
    def test_conformed_middle_initial_v_is_kept(self, raw):
        p = parse_conformed(raw)
        assert p.middle == ("V",)
        assert p.key_mi.endswith("|V")
        assert p.generational == frozenset()

    @pytest.mark.parametrize("raw", ["Mark V. Anquillare", "Robert V. Vitale", "Paul V. Stahlin"])
    def test_western_middle_initial_v_is_kept(self, raw):
        p = parse_western(raw)
        assert p.middle == ("V",)
        assert p.key_mi.endswith("|V")

    def test_v_and_a_real_suffix_on_the_same_name(self):
        # research 21 F7: "Stuart V. Flavin III" -- V is the middle initial, III the suffix.
        p = parse_western("Stuart V. Flavin III")
        assert (p.last, p.first, p.middle) == ("FLAVIN", "STUART", ("V",))
        assert p.generational == frozenset({"III"})
        assert parse_western("Stuart V Flavin").key_mi == p.key_mi  # veto, not the key, separates them

    def test_real_generational_suffixes_still_parse(self):
        p = parse_conformed("FLORSHEIM THOMAS W JR")
        assert (p.last, p.first, p.middle, p.generational) == ("FLORSHEIM", "THOMAS", ("W",), frozenset({"JR"}))
        w = parse_western("William T. Dillard III")
        assert (w.last, w.first, w.generational) == ("DILLARD", "WILLIAM", frozenset({"III"}))

    def test_credentials_are_suffixes_but_not_generational(self):
        p = parse_western("Jane Q. Public, CFA")
        assert p.last == "PUBLIC"
        assert "CFA" in p.suffixes
        assert p.generational == frozenset()


class TestEligibility:
    """Defect 3: DATE and BANK were missing, so two non-persons reached a tier."""

    @pytest.mark.parametrize("raw", ["Effective Date", "Manufacturers Bank"])
    def test_research_21_non_person_rows_are_ineligible(self, raw):
        assert not is_person_name_candidate(raw)

    @pytest.mark.parametrize(
        "raw",
        ["Chief Executive Officer", "President and Chief", "Acme Holdings LLC", "Board of Directors"],
    )
    def test_role_and_entity_text_stays_ineligible(self, raw):
        assert not is_person_name_candidate(raw)

    @pytest.mark.parametrize("raw", ["Timothy D. Cook", "Mark V. Anquillare", "Maria de la Cruz"])
    def test_person_names_are_eligible(self, raw):
        assert is_person_name_candidate(raw)

    def test_single_token_is_not_a_person_name(self):
        assert not is_person_name_candidate("Cook")


class TestConformedHonorifics:
    """Spec review S4: Form 3/4/5 filers put titles in the conformed name too."""

    def test_title_before_the_given_name_is_dropped(self):
        p = parse_conformed("Akbari Dr. Homaira")
        assert (p.last, p.first) == ("AKBARI", "HOMAIRA")

    def test_trailing_title_is_dropped(self):
        p = parse_conformed("PRICE BILLY L JR DR")
        assert (p.last, p.first, p.middle, p.generational) == ("PRICE", "BILLY", ("L",), frozenset({"JR"}))

    def test_hon_is_a_surname_in_conformed_form(self):
        assert parse_conformed("HON KWOK WAI").last == "HON"


class TestShape:
    def test_honorifics_are_dropped_in_western_form(self):
        p = parse_western("Dr. Jane Q. Public")
        assert (p.last, p.first, p.middle) == ("PUBLIC", "JANE", ("Q",))

    def test_digits_break_the_shape(self):
        assert not parse_conformed("SMITH JOHN 2").shape

    def test_empty_input(self):
        p = parse_western("")
        assert (p.last, p.first, p.shape, p.key_mi) == ("", "", False, "||")
