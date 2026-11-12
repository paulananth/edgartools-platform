"""Which rules a Mastering Policy may hold, and which verdicts may act alone.

A rule in a policy is **declared** until an `automatic_rules` entry lists one
of its verdicts: listed is on. A body is refused, by name and with its reason,
unless every rule is well formed and every entry names a rule version and
verdict the policy holds.
"""

from __future__ import annotations

import copy

import pytest

from edgar_warehouse.mdm.activation import (
    activated,
    check_policy,
    rule_version_conflicts,
)
from edgar_warehouse.mdm.sec_company import POLICY
from edgar_warehouse.mdm.primitives import UnknownPrimitive
from edgar_warehouse.mdm.store import Conflict, digest
from tests.mdm import policy_layers

RULE = {
    "rule_id": "sec-company",
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
                    "args": {"field": "entity_type", "values": ["operating"]},
                }
            ],
        },
        {"step": "2", "verdict": "deferred", "otherwise": True},
    ],
}

CIK_ACTIVATION = {
    "kind": "company",
    "family": "binding",
    "rule_id": "company-cik",
    "rule_version": "2026-09-24",
    "verdict": "bind",
}

def entry(**changes):
    body = {
        "kind": "company",
        "family": "classification",
        "rule_id": "sec-company",
        "rule_version": "2026-09-24",
        "verdict": "company",
    }
    body.update(changes)
    return body


def policy(rules=None, automatic=None):
    return {
        "version": "test",
        "required_consumers": ["journal"],
        "automatic_rules": automatic if automatic is not None else [],
        "kinds": {
            "company": {
                "version": "company-test",
                "rules": rules if rules is not None else [RULE],
            }
        },
    }


class TestADeclaredRuleIsWellFormed:
    def test_a_policy_declaring_rules_without_activating_them_passes(self):
        check_policy(policy())

    def test_an_unknown_primitive_is_refused_at_registration(self):
        """§10 check 1: refused when registered, not when a record reaches it."""
        rule = copy.deepcopy(RULE)
        rule["steps"][0]["when"][0]["primitive"] = "invented@1"
        with pytest.raises(UnknownPrimitive, match="invented@1"):
            check_policy(policy(rules=[rule]))

    def test_a_rule_without_exactly_one_catch_all_is_refused(self):
        """§10 check 2."""
        rule = {**RULE, "steps": RULE["steps"][:1]}
        with pytest.raises(Conflict, match="exactly one otherwise"):
            check_policy(policy(rules=[rule]))
        doubled = {**RULE, "steps": [*RULE["steps"], RULE["steps"][-1]]}
        with pytest.raises(Conflict, match="exactly one otherwise"):
            check_policy(policy(rules=[doubled]))

    def test_a_step_naming_an_undeclared_verdict_is_refused(self):
        rule = copy.deepcopy(RULE)
        rule["steps"][0]["verdict"] = "person"
        with pytest.raises(Conflict, match="person"):
            check_policy(policy(rules=[rule]))

    def test_a_catch_all_written_as_an_empty_when_is_refused(self):
        rule = copy.deepcopy(RULE)
        rule["steps"][0]["when"] = []
        with pytest.raises(Conflict, match="otherwise"):
            check_policy(policy(rules=[rule]))

    def test_two_rules_sharing_an_id_and_version_in_one_body_are_refused(self):
        with pytest.raises(Conflict, match="sec-company"):
            check_policy(policy(rules=[RULE, RULE]))

    def test_a_malformed_binding_rule_is_refused(self):
        binding = {"rule_id": "cik", "version": "1", "family": "binding"}
        with pytest.raises(Conflict, match="applies to"):
            check_policy(policy(rules=[RULE, binding]))


class TestARuleVersionNamesOneSetOfSteps:
    """§10 check 9: the pin the per-kind digest cannot provide."""

    def test_the_same_rule_registered_twice_is_not_a_conflict(self):
        assert rule_version_conflicts(policy(), [policy()]) == []

    def test_different_steps_under_one_version_are_refused(self):
        edited = copy.deepcopy(RULE)
        edited["steps"][0]["when"][0]["args"]["values"] = ["operating", "other"]
        assert rule_version_conflicts(policy(rules=[edited]), [policy()]) == [
            ("company", "sec-company", "2026-09-24")
        ]

    def test_a_new_version_is_free(self):
        edited = copy.deepcopy(RULE)
        edited["version"] = "2026-09-25"
        edited["steps"][0]["when"][0]["args"]["values"] = ["operating", "other"]
        assert rule_version_conflicts(policy(rules=[edited]), [policy()]) == []

    def test_a_body_with_no_kinds_block_holds_no_rules(self):
        assert rule_version_conflicts(policy(), [{"fields": {}}]) == []


class TestAListedVerdictIsOn:
    def test_a_listed_verdict_acts_alone(self):
        body = policy(automatic=[entry()])
        check_policy(body)
        assert activated(body, "company", RULE, "company")
        assert not activated(body, "company", RULE, "deferred")

    def test_nothing_is_active_without_an_entry(self):
        assert not activated(policy(), "company", RULE, "company")

    def test_an_entry_for_another_rule_version_does_not_activate_this_one(self):
        """An edited rule is a new version; the entry names the one that is on."""
        body = policy(automatic=[entry()])
        assert not activated(body, "company", {**RULE, "version": "x"}, "company")

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"rule_id": "absent"}, "absent"),
            ({"rule_version": "2026-09-23"}, "2026-09-23"),
            ({"verdict": "person"}, "person"),
            ({"family": "binding"}, "binding"),
            ({"kind": "fund"}, "fund"),
            ({"proof": {"n": 1}}, "names exactly"),
            ({"activation": "measured"}, "names exactly"),
        ],
    )
    def test_an_entry_that_does_not_hold_is_refused(self, changes, reason):
        with pytest.raises(Conflict, match=reason):
            check_policy(policy(automatic=[entry(**changes)]))

    def test_one_verdict_is_listed_once(self):
        """§10 check 6: no duplicate (kind, family, rule_id, verdict)."""
        with pytest.raises(Conflict, match="twice"):
            check_policy(policy(automatic=[entry(), entry()]))

    def test_a_bare_string_entry_is_refused(self):
        with pytest.raises(Conflict, match="entry"):
            check_policy(policy(automatic=["exact"]))


CIK_RULE = {
    "rule_id": "company-cik",
    "version": "2026-09-24",
    "family": "binding",
    "applies_to_verdict": "company",
    "emits": ["bind"],
    "on_no_match": "mint",
    "source": "sec.company.v1",
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "cik"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "cik"}},
    ],
}
CIK_CONTRACT = {
    "authority": "SEC/EDGAR",
    "sources": ["sec.company.v1"],
    "normalizer": "normalize_identifier@sec-cik-v1",
    "claim": {"forward": 1, "reverse": 1},
    "compatibility": {"field": "kind", "predicate": "kind_equal@1"},
}


def binding_policy(rule=None, contract=None, activate=True):
    body = policy(rules=[RULE, rule or CIK_RULE])
    if contract is not False:
        body["kinds"]["company"]["identifiers"] = {"cik": contract or CIK_CONTRACT}
    if activate:
        body["automatic_rules"] = [
            {
                "kind": "company",
                "family": "binding",
                "rule_id": "company-cik",
                "rule_version": "2026-09-24",
                "verdict": "bind",
            }
        ]
    return body


class TestAnIdentifierRule:
    """An identifier matching rule is on when listed and its Identifier Contract is complete."""

    def test_a_listed_rule_with_a_complete_contract_is_on(self):
        body = binding_policy()
        check_policy(body)
        assert activated(body, "company", CIK_RULE, "bind")

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"on_no_match": "guess"}, "on_no_match"),
            # Ticket 138 part A2a: what a record reaching several masters does.
            ({"on_several": "guess"}, "on_several"),
            # Part A2b: what a record reaching two masters it does not merge does.
            ({"on_conflict": "guess"}, "on_conflict"),
            # A merge only by an identifier stated to consolidate (a listing FIGI).
            ({"on_several": "merge"}, "consolidates: true"),
            ({"emits": ["bind", "consolidate"]}, "exactly bind"),
            ({"applies_to_verdict": "person"}, "sits in kind company"),
            # Record tests may narrow a binding rule (ticket 97), never stand for its identifier.
            (
                {"when": [{"primitive": "token_match@1", "args": {}}]},
                "exactly one namespace",
            ),
            (
                {"when": [{"primitive": "identifier_match@1", "args": {"namespace": "cik"}},
                          {"primitive": "gleif_entity_eligible@1", "args": {}}]},
                "neither a binding test nor a record test",
            ),
            (
                {
                    "when": [
                        {
                            "primitive": "identifier_match@1",
                            "args": {"namespace": "sec.cik"},
                        }
                    ]
                },
                "exactly one namespace",
            ),
            (
                {
                    "when": [
                        {
                            "primitive": "identifier_cardinality@1",
                            "args": {"namespace": "cik"},
                        }
                    ]
                },
                "does not match an identifier",
            ),
        ],
    )
    def test_a_malformed_rule_is_refused(self, changes, reason):
        with pytest.raises(Conflict, match=reason):
            check_policy(binding_policy(rule={**CIK_RULE, **changes}, activate=False))

    def test_a_rule_that_creates_companies_must_name_its_source(self):
        rule = {k: v for k, v in CIK_RULE.items() if k != "source"}
        with pytest.raises(Conflict, match="names no source"):
            check_policy(binding_policy(rule=rule, activate=False))

    def test_only_the_identifier_issuer_may_create_companies(self):
        # Ticket 11, gap 1: a GLEIF rule set to create would have minted a
        # Company from an unmatched LEI; an unlinked GLEIF record waits.
        rule = {**CIK_RULE, "source": "gleif.level1.v1"}
        with pytest.raises(Conflict, match="does not issue cik"):
            check_policy(binding_policy(rule=rule, activate=False))

    def test_only_the_identifier_issuer_may_merge_by_it(self):
        # Design 5 (operator, 2026-10-26: "Lookup only"): a value another
        # source files finds a master and never merges two.
        rule = {**CIK_RULE, "source": "gleif.level1.v1", "on_no_match": "wait", "on_several": "merge"}
        contract = {**CIK_CONTRACT, "consolidates": True}
        with pytest.raises(Conflict, match="merges only from its issuing source"):
            check_policy(binding_policy(rule=rule, contract=contract, activate=False))

    def test_a_rule_that_creates_companies_needs_its_kinds_contract(self):
        rule = {**CIK_RULE, "source": "gleif.level1.v1"}
        with pytest.raises(Conflict, match="no Identifier Contract"):
            check_policy(binding_policy(rule=rule, contract=False, activate=False))

    def test_a_rule_that_only_joins_may_come_from_any_source(self):
        rule = {**CIK_RULE, "on_no_match": "wait", "source": "gleif.level1.v1"}
        check_policy(binding_policy(rule=rule, activate=False))

    def test_a_new_identifier_needs_only_its_contract_and_rule(self):
        """Operator, 2026-10-09: "Read the list from the rules". A namespace with
        an Identifier Contract may be matched on, with no code; its name is
        lower-case words, since binding reads it as a JSON key in SQL."""
        def renamed(name):
            rule = {**CIK_RULE, "when": [{**t, "args": {"namespace": name}} for t in CIK_RULE["when"]]}
            body = binding_policy(rule=rule, activate=False)
            body["kinds"]["company"]["identifiers"] = {name: CIK_CONTRACT}
            return body

        check_policy(renamed("crd"))
        with pytest.raises(Conflict, match="lower-case words"):
            check_policy(renamed("crd'); DROP"))
        with pytest.raises(Conflict, match="no Identifier Contract"):
            check_policy(binding_policy(rule={**CIK_RULE, "when": [
                {**t, "args": {"namespace": "crd"}} for t in CIK_RULE["when"]]}, activate=False))

    def test_a_listed_rule_needs_its_contract(self):
        with pytest.raises(Conflict, match="no Identifier Contract"):
            check_policy(binding_policy(contract=False))

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"authority": ""}, "authority"),
            ({"sources": []}, "issuing source"),
            ({"normalizer": "invented"}, "normalizer"),
            ({"claim": {}}, "forward claim"),
            (
                {"compatibility": {"field": "kind", "predicate": "token_match@1"}},
                "compatibility",
            ),
        ],
    )
    def test_an_incomplete_contract_is_refused(self, changes, reason):
        with pytest.raises(Conflict, match=reason):
            check_policy(binding_policy(contract={**CIK_CONTRACT, **changes}))

class TestTheCompanyPolicy:
    def test_the_company_rule_acts_alone_only_on_its_company_verdict(self):
        check_policy(POLICY)
        (rule,) = [
            r
            for r in POLICY["kinds"]["company"]["rules"]
            if r["rule_id"] == "sec-company-candidate"
        ]
        assert activated(POLICY, "company", rule, "company")
        assert not activated(POLICY, "company", rule, "deferred")
        assert POLICY["automatic_rules"][1] == CIK_ACTIVATION


@pytest.mark.parametrize("changes", [
    {"compare": ["street", "county"]},
    {"compare": [["city", "county"]]},
    {"compare": [[]]},
    {"compare": [["city", ["postcode"]]]},
    {"over_shared": 0},
    {"refused_flags": ["anything"]},
    {"pass": None},
])
def test_a_cascade_pass_with_invalid_arguments_is_refused(changes):
    from edgar_warehouse.mdm.activation import check_name_binding_rule

    rule = copy.deepcopy(next(r for r in POLICY["kinds"]["company"]["rules"]
                              if r["rule_id"] == "sec-gleif-name-city-or-postcode"))
    rule["when"][0]["args"] = {**rule["when"][0]["args"], **changes}
    with pytest.raises(Conflict, match="invalid pass arguments"):
        check_name_binding_rule("company", rule, POLICY["kinds"])


def test_a_cascade_pass_must_keep_the_one_lei_veto():
    from edgar_warehouse.mdm.activation import check_name_binding_rule

    rule = copy.deepcopy(next(r for r in POLICY["kinds"]["company"]["rules"]
                              if r["rule_id"] == "sec-gleif-name-city-or-postcode"))
    rule["when"] = [t for t in rule["when"] if t["primitive"] != "holds_no_other_lei@1"]
    with pytest.raises(Conflict, match="one-LEI veto"):
        check_name_binding_rule("company", rule, POLICY["kinds"])


def test_two_cascade_passes_with_one_name_are_refused():
    from edgar_warehouse.mdm.activation import check_policy

    body = copy.deepcopy(POLICY)
    rules = body["kinds"]["company"]["rules"]
    second = copy.deepcopy(next(r for r in rules if r["rule_id"] == "sec-gleif-name-city-or-postcode"))
    second["rule_id"] = "sec-gleif-name-city-or-postcode-again"
    rules.append(second)
    with pytest.raises(Conflict, match="must be unique"):
        check_policy(body)


def test_kinds_that_read_one_namespace_differently_are_refused():
    """Platform validation 05a: the Merge Stage looks a CIK up across every
    kind that declares one, so their contracts must agree."""
    body = copy.deepcopy(POLICY)
    company = body["kinds"]["company"]
    person = body["kinds"]["person"]
    agreed = person["identifiers"]["cik"]
    person["identifiers"] = {"cik": {**agreed, "normalizer": "normalize_identifier@lei-v1"}}
    with pytest.raises(Conflict, match="different authority or normalizer"):
        check_policy(body)
    person["identifiers"]["cik"] = agreed
    check_policy(body)


# The exact-name family (ticket 01): a name finds a master, never creates one.
EXACT_RULE = {"rule_id": "name-finds-master", "version": "v1", "family": "exact_name_binding", "source": "a.v1",
              "holder_sources": ["b.v1"], "applies_to_verdict": "company", "emits": ["bind"], "key": "name_id@1",
              "on_no_match": "wait", "on_several": "review"}
EXACT_ENTRY = {"kind": "company", "family": "exact_name_binding", "rule_id": "name-finds-master", "rule_version": "v1",
               "verdict": "bind"}


def exact_policy(**rule_changes) -> dict:
    body = copy.deepcopy(policy_layers.with_rules_on(__import__("edgar_warehouse.rules.files", fromlist=["x"]).policy(), "company"))
    body["kinds"]["company"]["rules"].append({**EXACT_RULE, **rule_changes})
    return body


def test_an_exact_name_rule_that_finds_and_never_creates_is_accepted():
    body = exact_policy()
    body["automatic_rules"].append(copy.deepcopy(EXACT_ENTRY))
    check_policy(body)


def test_an_exact_name_rule_that_mints_when_no_master_holds_the_name_is_accepted():
    body = exact_policy(on_no_match="mint")
    body["automatic_rules"].append(copy.deepcopy(EXACT_ENTRY))
    check_policy(body)


@pytest.mark.parametrize("change", [
    {"on_no_match": "guess"}, {"cross_reference": "Name Form"}, {"cross_reference": "a_name_that_is_far_too_long"}, {"on_several": "bind"}, {"holder_sources": []}, {"holder_sources": ["a.v1"]},
    {"key": "name"}, {"when": [{"primitive": "identifier_match@1", "args": {"namespace": "lei"}}]},
    {"emits": ["bind", "create"]},
])
def test_an_exact_name_rule_that_could_guess_is_refused(change):
    with pytest.raises(Conflict):
        check_policy(exact_policy(**change))
