"""The fixed vocabulary a Mastering Policy names and code implements.

Structure and parameters live in the policy document; the tests themselves live
here. A document names a primitive as `name@version` and the registry refuses a
pair it does not hold, so a policy can never reach a test that is not in the
build (`policy-language.md` §5).

Behaviour is pinned against the throwaway prototype
(`.scratch/mastering-policy-language/prototype/interpret.mjs`), which reproduced
research 18's measured classification to the row: 841/841 person, 353/353
entity over 1,220 labelled records.
"""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.clean.primitives import (
    REGISTRY,
    UnknownPrimitive,
    call,
    normalizer,
)
from edgar_warehouse.mdm.clean.store import Conflict

CONFORMED = "normalize_text@edgar-conformed-v1"

DOC = {
    "lists": {
        "legal_forms": ["INC", "CORP", "TRUST", "HOLDINGS", "LLC", "AND"],
        "ambiguous": ["TRUST"],
        "person_suffixes": ["JR", "SR", "III", "MD"],
        "structural": ["state_of_incorporation", "fiscal_year_end"],
    },
    "normalizers": {},
}


class TestTheRegistry:
    def test_a_primitive_is_named_with_its_version(self):
        assert "token_match@1" in REGISTRY
        assert "token_match" not in REGISTRY

    def test_an_unknown_pair_is_refused_by_name(self):
        with pytest.raises(UnknownPrimitive, match="invented@1"):
            call("invented@1", {}, {}, DOC)

    def test_an_unknown_version_of_a_known_primitive_is_refused(self):
        """A corrected primitive is a new version; the old one is never edited."""
        with pytest.raises(UnknownPrimitive, match="token_match@99"):
            call("token_match@99", {}, {}, DOC)

    def test_every_primitive_declares_the_family_it_belongs_to(self):
        families = {p.family for p in REGISTRY.values()}
        assert families <= {"shared", "classification", "binding", "survivorship"}

    def test_the_registry_is_not_mutable_by_a_caller(self):
        with pytest.raises((TypeError, AttributeError)):
            REGISTRY["token_match@1"] = None


class TestNormalizers:
    def test_a_conformed_name_is_upper_cased_and_punctuation_becomes_space(self):
        assert normalizer(CONFORMED, DOC)("Acme Co., Inc.") == "ACME CO INC"

    def test_an_ampersand_becomes_the_word_and(self):
        """EDGAR conformed names normalize `&`, so a declared list carries AND."""
        assert normalizer(CONFORMED, DOC)("Smith & Wesson") == "SMITH AND WESSON"

    def test_a_cik_loses_its_leading_zeros(self):
        assert normalizer("normalize_identifier@sec-cik-v1", DOC)("0000320193") == "320193"

    def test_an_lei_is_upper_cased_and_stripped(self):
        assert (
            normalizer("normalize_identifier@lei-v1", DOC)("hwupkr0mpou8fgxbt394")
            == "HWUPKR0MPOU8FGXBT394"
        )

    def test_an_unknown_normalizer_is_refused(self):
        with pytest.raises(UnknownPrimitive):
            normalizer("normalize_text@invented", DOC)


class TestClassificationPrimitives:
    def evaluate(self, name, args, record):
        return call(name, args, record, DOC)

    def test_evidence_present_sees_a_value(self):
        assert self.evaluate("evidence_present@1", {"document": "sub"}, {"sub": {"a": 1}})
        assert not self.evaluate("evidence_present@1", {"document": "sub"}, {"sub": {}})
        assert not self.evaluate("evidence_present@1", {"document": "sub"}, {})

    def test_field_in_set_matches_a_declared_value(self):
        args = {"field": "entity_type", "values": ["operating", "investment"]}
        assert self.evaluate("field_in_set@1", args, {"entity_type": "operating"})
        assert not self.evaluate("field_in_set@1", args, {"entity_type": "individual"})

    def test_token_match_finds_a_legal_form_as_a_whole_token(self):
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "token_list": "legal_forms",
            "min_count": 1,
        }
        assert self.evaluate("token_match@1", args, {"name": "Acme Holdings Inc"})
        assert not self.evaluate("token_match@1", args, {"name": "Vincent Palmer"})

    def test_a_declared_form_inside_a_longer_word_is_not_a_token(self):
        """INC must not match INCORPORATED, nor a surname containing a form."""
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "token_list": "legal_forms",
            "min_count": 1,
        }
        assert not self.evaluate("token_match@1", args, {"name": "Incandescent Bulbs"})
        assert not self.evaluate("token_match@1", args, {"name": "Trustman Paul"})

    def test_token_match_without_a_count_is_refused_rather_than_always_true(self):
        """A test that decides an entity's kind may not silently pass."""
        with pytest.raises(Conflict, match="min_count or max_count"):
            self.evaluate(
                "token_match@1",
                {
                    "field": "name",
                    "normalizer": CONFORMED,
                    "token_list": "legal_forms",
                },
                {"name": "Vincent Palmer"},
            )

    def test_token_match_counts_can_demand_exactly_one(self):
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "token_list": "legal_forms",
            "min_count": 1,
            "max_count": 1,
        }
        assert self.evaluate("token_match@1", args, {"name": "Acme Trust"})
        assert not self.evaluate("token_match@1", args, {"name": "Acme Holdings Inc"})

    def test_token_match_can_exclude_an_ambiguous_word(self):
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "token_list": "legal_forms",
            "exclude_list": "ambiguous",
            "min_count": 1,
        }
        assert not self.evaluate("token_match@1", args, {"name": "Acme Trust"})
        assert self.evaluate("token_match@1", args, {"name": "Acme Inc"})

    def test_an_ampersand_is_its_own_signal(self):
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "token_list": "legal_forms",
            "min_count": 1,
        }
        assert self.evaluate("token_match@1", args, {"name": "Smith & Wesson"})

    def test_name_shape_accepts_a_two_token_person_name(self):
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "min_tokens": 2,
            "max_tokens": 5,
            "suffix_list": "person_suffixes",
        }
        assert self.evaluate("name_shape@1", args, {"name": "Palmer Vincent"})
        assert not self.evaluate("name_shape@1", args, {"name": "Palmer"})

    def test_name_shape_needs_two_tokens_that_are_not_suffixes(self):
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "min_tokens": 2,
            "max_tokens": 5,
            "suffix_list": "person_suffixes",
        }
        assert not self.evaluate("name_shape@1", args, {"name": "Palmer Jr"})
        assert self.evaluate("name_shape@1", args, {"name": "Palmer Vincent Jr"})

    def test_name_shape_checks_digits_on_the_raw_text(self):
        """Tokenizing first would delete the very characters being checked."""
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "min_tokens": 2,
            "max_tokens": 5,
            "suffix_list": "person_suffixes",
            "forbid_digits": {"value": True},
        }
        assert not self.evaluate("name_shape@1", args, {"name": "Palmer Vincent 3"})
        assert self.evaluate("name_shape@1", args, {"name": "Palmer Vincent"})

    def test_name_shape_can_forbid_a_named_character(self):
        args = {
            "field": "name",
            "normalizer": CONFORMED,
            "min_tokens": 2,
            "max_tokens": 5,
            "suffix_list": "person_suffixes",
            "forbid_characters": {"value": ["&"]},
        }
        assert not self.evaluate("name_shape@1", args, {"name": "Smith & Wesson"})

    def test_fields_all_empty_reads_declared_paths(self):
        args = {"fields": "structural"}
        assert self.evaluate("fields_all_empty@1", args, {"state_of_incorporation": ""})
        assert not self.evaluate(
            "fields_all_empty@1", args, {"state_of_incorporation": "DE"}
        )

    def test_fields_all_empty_accepts_an_inline_list(self):
        args = {"fields": ["a", "b"]}
        assert self.evaluate("fields_all_empty@1", args, {"a": None, "b": ""})
        assert not self.evaluate("fields_all_empty@1", args, {"a": None, "b": "x"})

    def test_a_dotted_path_reads_a_nested_field(self):
        args = {"field": "sub.entityType", "values": ["operating"]}
        assert self.evaluate("field_in_set@1", args, {"sub": {"entityType": "operating"}})


class TestWhatTheVocabularyRefuses:
    """§5: the digest must reproduce a result, so a document supplies no code."""

    def test_a_document_supplied_regular_expression_is_not_a_primitive(self):
        assert not any(name.startswith("regex") for name in REGISTRY)

    def test_a_list_a_document_names_but_does_not_declare_is_refused(self):
        with pytest.raises(Conflict, match="undeclared_list"):
            call(
                "token_match@1",
                {
                    "field": "name",
                    "normalizer": CONFORMED,
                    "token_list": "undeclared_list",
                    "min_count": 1,
                },
                {"name": "Acme Inc"},
                DOC,
            )
