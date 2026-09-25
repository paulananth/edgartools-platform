"""A record's identity kind, decided by a governed rule rather than a table.

A Dataset Contract names one classification rule; the Mastering Policy holds
it. The rule is an ordered list of steps, and the first step whose `when`
conjunction holds supplies the verdict (`policy-language.md` §6). The decided
kind is then stamped on the assertion and hashed into its id, so it is settled
when the record is read and never afterwards.
"""

from __future__ import annotations

import copy
from typing import ClassVar

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


class TestTheReadPathRunsTheNamedRule:
    """A Dataset Contract names a rule; the record keeps the rule that labelled it."""

    COMPANY_RULE: ClassVar[dict] = {
        "rule_id": "sec-company-candidate",
        "version": "2026-09-24",
        "family": "classification",
        "emits": ["company", "deferred"],
        "steps": [
            {
                "step": "1",
                "verdict": "company",
                "when": [
                    {
                        "primitive": "field_in_set@1",
                        "args": {
                            "field": "entity_type",
                            "values": ["operating", "investment"],
                        },
                    }
                ],
            },
            {"step": "2", "verdict": "deferred", "otherwise": True},
        ],
    }

    def policy(self, active=False):
        from tests.mdm.test_clean_activation import BAR, proof

        automatic = []
        if active:
            automatic = [
                {
                    "kind": "company",
                    "family": "classification",
                    "rule_id": "sec-company-candidate",
                    "rule_version": "2026-09-24",
                    "verdict": "company",
                    "activation": "measured",
                    "proof": proof(),
                }
            ]
        return {
            "required_consumers": ["journal"],
            "automatic_rules": automatic,
            "kinds": {
                "company": {
                    "version": "company-test",
                    "rules": [self.COMPANY_RULE],
                    "bars": {"classification": BAR},
                }
            },
        }

    def contract(self):
        import copy

        from edgar_warehouse.mdm.clean.company_source import CONTRACT

        contract = copy.deepcopy(CONTRACT)
        contract["adapter"]["classification"] = {
            "kind": "company",
            "rule_id": "sec-company-candidate",
            "version": "2026-09-24",
        }
        return contract

    def read(self, row, policy):
        from edgar_warehouse.mdm.clean.adapters import normalize

        return normalize(
            row,
            source_code="sec.submissions.company.v1",
            contract=self.contract(),
            publication={
                "publication_key": "p",
                "revision": 0,
                "artifact_sha256": "c" * 64,
                "member": "m",
            },
            policy=policy,
        )

    ROW: ClassVar[dict] = {
        "cik": 320193,
        "entity_type": "operating",
        "entity_name": "Apple Inc.",
    }

    def test_an_activated_verdict_becomes_the_kind_and_names_its_rule(self):
        body = self.read(self.ROW, self.policy(active=True))
        assert body["kind"] == "company"
        assert body["provenance"]["classification"] == {
            "rule_id": "sec-company-candidate",
            "version": "2026-09-24",
            "step": "1",
        }

    def test_a_verdict_not_activated_is_set_aside_with_its_rule(self):
        from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

        with pytest.raises(UnsupportedRecord) as caught:
            self.read(self.ROW, self.policy())
        assert caught.value.reason == "classification_not_activated"
        assert caught.value.detail["classification"]["verdict"] == "company"

    def test_a_verdict_that_decides_no_kind_is_set_aside_by_that_verdict(self):
        from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

        with pytest.raises(UnsupportedRecord) as caught:
            self.read({**self.ROW, "entity_type": "other"}, self.policy(active=True))
        assert caught.value.reason == "classification_deferred"
        assert caught.value.detail["classification"]["step"] == "2"

    def test_a_rule_written_for_another_source_is_refused(self):
        self.COMPANY_RULE["source"] = "gleif.level1.v1"
        try:
            with pytest.raises(Conflict, match="written for gleif.level1.v1"):
                self.read(self.ROW, self.policy(active=True))
        finally:
            del self.COMPANY_RULE["source"]

    def test_a_named_rule_without_its_policy_fails_closed(self):
        with pytest.raises(Conflict, match="pinned Mastering Policy"):
            self.read(self.ROW, None)

    def test_the_rule_is_part_of_the_record_identity(self):
        """Same claim, labelled by a rule instead of a table: a different id."""
        from edgar_warehouse.mdm.clean.adapters import normalize
        from edgar_warehouse.mdm.clean.company_source import CONTRACT

        by_rule = self.read(self.ROW, self.policy(active=True))
        legacy_contract = copy.deepcopy(CONTRACT)
        legacy_contract["adapter"].pop("classification")
        legacy_contract["adapter"]["kind_field"] = "entity_type"
        legacy_contract["adapter"]["kind_values"] = {"operating": "company"}
        by_table = normalize(
            self.ROW,
            source_code="sec.submissions.company.v1",
            contract=legacy_contract,
            publication={
                "publication_key": "p",
                "revision": 0,
                "artifact_sha256": "c" * 64,
                "member": "m",
            },
        )
        assert by_table["kind"] == by_rule["kind"] == "company"
        assert "classification" not in by_table["provenance"]
        assert by_table["assertion_id"] != by_rule["assertion_id"]


class TestProbableKind:
    """A held-back record says what it probably is (CONTEXT.md, Probable Kind).

    It sorts the Stage and never creates an identity: the kind's own rule
    decides, with its own bar.
    """

    RULE: ClassVar[dict] = {
        **TestTheReadPathRunsTheNamedRule.COMPANY_RULE,
        "steps": [
            {
                "step": "0",
                "verdict": "deferred",
                "probable_kind": "fund_structure",
                "when": [
                    {
                        "primitive": "field_in_set@1",
                        "args": {"field": "entity_type", "values": ["investment"]},
                    }
                ],
            },
            *TestTheReadPathRunsTheNamedRule.COMPANY_RULE["steps"],
        ],
    }

    def read(self, row, *, active=False):
        reader = TestTheReadPathRunsTheNamedRule()
        policy = reader.policy(active=active)
        policy["kinds"]["company"]["rules"] = [self.RULE]
        return reader.read(row, policy)

    def test_a_step_that_holds_a_record_back_names_its_probable_kind(self):
        from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

        with pytest.raises(UnsupportedRecord) as caught:
            self.read({"cik": 1, "entity_type": "investment", "entity_name": "X"})
        assert caught.value.reason == "classification_deferred"
        assert caught.value.probable_kind == "fund_structure"

    def test_a_kind_the_policy_has_not_switched_on_is_the_probable_kind(self):
        from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

        with pytest.raises(UnsupportedRecord) as caught:
            self.read({"cik": 1, "entity_type": "operating", "entity_name": "X"})
        assert caught.value.reason == "classification_not_activated"
        assert caught.value.probable_kind == "company"

    def test_a_step_with_no_probable_kind_leaves_it_unknown(self):
        from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

        with pytest.raises(UnsupportedRecord) as caught:
            self.read({"cik": 1, "entity_type": "other", "entity_name": "X"})
        assert caught.value.probable_kind is None

    def test_a_step_that_decides_a_kind_may_not_also_name_one(self):
        steps = copy.deepcopy(RULE["steps"])
        steps[1]["probable_kind"] = "person"
        with pytest.raises(Conflict, match="belongs only to a step"):
            classify({**RULE, "steps": steps}, record(), DOC)

    def test_a_probable_kind_that_is_not_a_kind_is_refused(self):
        steps = copy.deepcopy(RULE["steps"])
        steps[0]["probable_kind"] = "fund"
        with pytest.raises(Conflict, match="not a kind"):
            classify({**RULE, "steps": steps}, record(), DOC)


class TestAWaitingRecordKeepsItsProbableKind:
    ARGS: ClassVar[dict] = {
        "source_code": "s",
        "publication_key": "p",
        "record_locator": "r",
        "schema_version": "v",
        "reason": "classification_deferred",
        "raw_record": {"cik": 1},
        "provenance": {},
    }

    def test_a_record_with_none_keeps_the_id_it_had_before(self):
        from edgar_warehouse.mdm.clean.evidence import deferred_record
        from edgar_warehouse.mdm.clean.store import digest

        body = deferred_record(**self.ARGS)
        assert "probable_kind" not in body
        assert body["deferred_id"] == digest(dict(self.ARGS))

    def test_it_is_part_of_the_record(self):
        from edgar_warehouse.mdm.clean.evidence import (
            deferred_record,
            validate_deferred,
        )

        body = deferred_record(**self.ARGS, probable_kind="person")
        assert body["probable_kind"] == "person"
        assert body["deferred_id"] != deferred_record(**self.ARGS)["deferred_id"]
        validate_deferred(body)

    def test_a_value_that_is_not_a_kind_is_refused(self):
        from edgar_warehouse.mdm.clean.evidence import deferred_record

        with pytest.raises(ValueError, match="not a kind"):
            deferred_record(**self.ARGS, probable_kind="fund")
