"""A record's identity kind, decided by a governed rule rather than a table.

A Dataset Contract names one classification rule; the Mastering Policy holds
it. The rule is an ordered list of steps, and the first step whose `when`
conjunction holds supplies the verdict (`policy-language.md` §6). The decided
kind is then stamped on the assertion and hashed into its id, so it is settled
when the record is read and never afterwards.
"""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.clean.classification import classify, resolve_rule
from edgar_warehouse.mdm.clean.primitives import UnknownPrimitive
from edgar_warehouse.mdm.clean.store import Conflict

DOC = {
    "lists": {
        "legal_forms": ["INC", "CORP", "TRUST", "HOLDINGS", "LLC"],
        "ambiguous": ["TRUST"],
        "person_suffixes": ["JR", "SR", "III"],
        "structural": ["state_of_incorporation", "fiscal_year_end"],
    },
    "normalizers": {"conformed": "normalize_text@edgar-conformed-v1"},
}

RULE = {
    "rule_id": "C-J",
    "version": "2026-09-20",
    "family": "classification",
    "source": "sec.ownership_reporting_owner",
    "emits": ["person", "company", "entity_undetermined", "deferred"],
    "steps": [
        {
            "step": "0",
            "verdict": "deferred",
            "when": [
                {
                    "primitive": "evidence_present@1",
                    "negate": True,
                    "args": {"document": "submissions"},
                }
            ],
        },
        {
            "step": "1",
            "verdict": "company",
            "when": [
                {
                    "primitive": "field_in_set@1",
                    "args": {
                        "field": "submissions.entityType",
                        "values": ["operating", "investment"],
                    },
                }
            ],
        },
        {
            "step": "2",
            "verdict": "entity_undetermined",
            "when": [
                {
                    "primitive": "token_match@1",
                    "args": {
                        "field": "name",
                        "normalizer": "conformed",
                        "token_list": "legal_forms",
                        "exclude_list": "ambiguous",
                        "min_count": 1,
                    },
                }
            ],
        },
        {
            "step": "3",
            "verdict": "person",
            "when": [
                {
                    "primitive": "fields_all_empty@1",
                    "args": {"fields": "structural"},
                },
                {
                    "primitive": "name_shape@1",
                    "args": {
                        "field": "name",
                        "normalizer": "conformed",
                        "min_tokens": 2,
                        "max_tokens": 5,
                        "suffix_list": "person_suffixes",
                        "forbid_digits": {"value": True},
                    },
                },
            ],
        },
        {"step": "4", "verdict": "deferred", "otherwise": True},
    ],
}


def record(**changes):
    base = {
        "submissions": {"entityType": "individual"},
        "name": "Palmer Vincent",
        "state_of_incorporation": "",
        "fiscal_year_end": "",
    }
    base.update(changes)
    return base


class TestFirstStepWins:
    def test_an_owner_with_no_captured_submissions_defers(self):
        assert classify(RULE, {"name": "Palmer Vincent"}, DOC) == "deferred"

    def test_sec_saying_operating_company_settles_it(self):
        assert (
            classify(RULE, record(submissions={"entityType": "operating"}), DOC)
            == "company"
        )

    def test_a_legal_form_in_the_name_is_not_a_person(self):
        assert (
            classify(RULE, record(name="Acme Holdings Inc"), DOC)
            == "entity_undetermined"
        )

    def test_a_person_shaped_name_with_no_structural_fields_is_a_person(self):
        assert classify(RULE, record(), DOC) == "person"

    def test_anything_else_falls_to_the_catch_all(self):
        assert classify(RULE, record(name="X"), DOC) == "deferred"

    def test_an_ambiguous_word_alone_does_not_make_it_an_entity(self):
        """TRUST is excluded, so the name falls through to the person test."""
        assert classify(RULE, record(name="Trust Palmer"), DOC) == "person"

    def test_a_structural_field_stops_it_being_a_person(self):
        assert classify(RULE, record(state_of_incorporation="DE"), DOC) == "deferred"

    def test_an_earlier_step_wins_over_a_later_one(self):
        """Company is decided at step 1 even though the name is person shaped."""
        assert (
            classify(RULE, record(submissions={"entityType": "operating"}), DOC)
            == "company"
        )


class TestWhatARuleMayNotBe:
    def rule_without(self, **changes):
        return {**RULE, **changes}

    def test_a_rule_with_no_catch_all_is_refused(self):
        with pytest.raises(Conflict, match="catch-all"):
            classify(self.rule_without(steps=RULE["steps"][:-1]), record(), DOC)

    def test_a_catch_all_written_as_an_empty_when_does_not_count(self):
        """Prototype finding 3: an empty list is easy to mis-edit into silence.

        The rule is refused for having no catch-all, which names what the
        author has to add rather than complaining about the empty list.
        """
        steps = [*RULE["steps"][:-1], {"step": "4", "verdict": "deferred", "when": []}]
        with pytest.raises(Conflict, match="catch-all"):
            classify(self.rule_without(steps=steps), record(), DOC)

    def test_an_empty_when_on_an_earlier_step_is_refused_when_reached(self):
        steps = [
            {"step": "0", "verdict": "person", "when": []},
            *RULE["steps"][-1:],
        ]
        with pytest.raises(Conflict, match="otherwise"):
            classify(self.rule_without(steps=steps), record(), DOC)

    def test_a_verdict_the_rule_does_not_declare_is_refused(self):
        steps = [
            {"step": "0", "verdict": "security", "otherwise": True},
        ]
        with pytest.raises(Conflict, match="security"):
            classify(self.rule_without(steps=steps), record(), DOC)

    def test_a_step_naming_an_unknown_primitive_is_refused(self):
        steps = [
            {
                "step": "0",
                "verdict": "person",
                "when": [{"primitive": "invented@1", "args": {}}],
            },
            *RULE["steps"][-1:],
        ]
        with pytest.raises(UnknownPrimitive):
            classify(self.rule_without(steps=steps), record(), DOC)

    def test_a_binding_rule_is_not_a_classification_rule(self):
        with pytest.raises(Conflict, match="classification"):
            classify(self.rule_without(family="binding"), record(), DOC)

    def test_a_step_may_not_call_a_survivorship_primitive(self):
        """Source rank is never an input to what a record is."""
        steps = [
            {
                "step": "0",
                "verdict": "person",
                "when": [{"primitive": "select_by_source_rank@1", "args": {}}],
            },
            *RULE["steps"][-1:],
        ]
        with pytest.raises(UnknownPrimitive):
            classify(self.rule_without(steps=steps), record(), DOC)


class TestResolvingTheRuleADatasetContractNames:
    def policy(self):
        return {"kinds": {"person": {"version": "person-1", "rules": [RULE]}}}

    def test_a_contract_names_a_rule_by_kind_id_and_version(self):
        named = {"kind": "person", "rule_id": "C-J", "version": "2026-09-20"}
        assert resolve_rule(self.policy(), named)["rule_id"] == "C-J"

    def test_a_named_rule_that_is_absent_is_refused(self):
        named = {"kind": "person", "rule_id": "C-Q", "version": "2026-09-20"}
        with pytest.raises(Conflict, match="C-Q"):
            resolve_rule(self.policy(), named)

    def test_a_named_version_that_is_absent_is_refused(self):
        """A rule edit mints a new version; it never inherits the old proof."""
        named = {"kind": "person", "rule_id": "C-J", "version": "2026-09-21"}
        with pytest.raises(Conflict, match="2026-09-21"):
            resolve_rule(self.policy(), named)

    def test_a_contract_naming_no_rule_keeps_the_adapters_own_mapping(self):
        assert resolve_rule(self.policy(), None) is None
