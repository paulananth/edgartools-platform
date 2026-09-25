"""Which rules a Mastering Policy may hold, and which verdicts may act alone.

A rule in a policy is **declared** until an `automatic_rules` entry makes one
of its verdicts **active** (`policy-language.md` §9). This module is the check
that replaces the blanket refusal: a body is refused, by name and with its
reason, unless every rule is well formed (§10) and every activation carries a
proof whose arithmetic holds against the kind's accepted bar (§9.2).

What it verifies is arithmetic, not truth: a fabricated `n: 1000, correct:
1000` passes. Attribution and an outside re-score are the defences (§9.2).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean.activation import (
    _check_proof,
    activated,
    check_policy,
    rule_version_conflicts,
    wilson_lower_bound,
)
from edgar_warehouse.mdm.clean.classification import fired
from edgar_warehouse.mdm.clean.company_source import APPROVED_ACTIVATION, POLICY, PROOF
from edgar_warehouse.mdm.clean.primitives import UnknownPrimitive
from edgar_warehouse.mdm.clean.store import Conflict, digest

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

BAR = {
    "min_precision": 0.999,
    "method": "wilson_lower_bound",
    "one_sided_confidence": 0.95,
}


def proof(n=3000, correct=3000, confidence=0.95, **changes):
    if "lower_bound" not in changes and 0 <= correct <= n:
        # Rounded down: a stated bound may never exceed its sample.
        changes["lower_bound"] = (
            math.floor(wilson_lower_bound(correct, n, confidence) * 1e6) / 1e6
        )
    body = {
        "method": "wilson_lower_bound",
        "one_sided_confidence": confidence,
        "n": n,
        "correct": correct,
        "lower_bound": None,
        "adversarial": {"fixture_sha256": "a" * 64, "violations": 0},
        "cohort": {
            "files": {"sample.jsonl": "b" * 64},
            # One sample per rule step, for every step id a test rule or the
            # Company policy uses ("0" to "10").
            "by_step": {
                str(step): {
                    "n": n,
                    "correct": correct,
                    "lower_bound": changes.get("lower_bound"),
                }
                for step in range(11)
            },
        },
        "approved_by": "operator",
        "approved_at": "2026-09-24T12:00:00Z",
        "reason": "fixture proof: arithmetic only, not a measurement",
    }
    body.update(changes)
    return body


def entry(**changes):
    body = {
        "kind": "company",
        "family": "classification",
        "rule_id": "sec-company",
        "rule_version": "2026-09-24",
        "verdict": "company",
        "activation": "measured",
        "proof": proof(),
    }
    body.update(changes)
    return body


def policy(rules=None, automatic=None, bars=None):
    return {
        "version": "test",
        "required_consumers": ["journal"],
        "automatic_rules": automatic if automatic is not None else [],
        "kinds": {
            "company": {
                "version": "company-test",
                "rules": rules if rules is not None else [RULE],
                "bars": bars if bars is not None else {"classification": BAR},
            }
        },
    }


class TestTheArithmetic:
    def test_a_perfect_sample_reproduces_the_spec_example(self):
        """`policy-language.md` §9.2: n 841, all correct, 97.5% -> 0.99545."""
        assert round(wilson_lower_bound(841, 841, 0.975), 5) == 0.99545

    def test_the_spec_example_passes_the_check_as_written(self):
        """§9.2's own entry states 0.99545, five decimals of 0.9954530."""
        body = {
            "required_consumers": ["journal"],
            "kinds": {
                "person": {
                    "rules": [
                        {
                            **RULE,
                            "emits": ["person", "deferred"],
                            "steps": [
                                {**RULE["steps"][0], "verdict": "person"},
                                RULE["steps"][1],
                            ],
                        }
                    ],
                    "bars": {
                        "classification": {
                            "min_precision": 0.99,
                            "method": "wilson_lower_bound",
                            "one_sided_confidence": 0.975,
                        }
                    },
                }
            },
            "automatic_rules": [
                entry(
                    kind="person",
                    verdict="person",
                    proof=proof(
                        n=841, correct=841, confidence=0.975, lower_bound=0.99545
                    ),
                )
            ],
        }
        check_policy(body)

    def test_a_bound_rounded_up_past_its_sample_is_refused(self):
        with pytest.raises(Conflict, match="does not reproduce"):
            check_policy(policy(automatic=[entry(proof=proof(lower_bound=0.99910))]))

    def test_a_perfect_sample_of_3000_clears_the_company_bar(self):
        assert wilson_lower_bound(3000, 3000, 0.95) >= 0.999

    def test_a_perfect_sample_of_1000_does_not(self):
        """Company's 99.9% bar needs a sample, not a clean streak of any size."""
        assert wilson_lower_bound(1000, 1000, 0.95) < 0.999


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


class TestAnActivationCarriesItsProof:
    def test_a_measured_activation_that_clears_the_bar_passes(self):
        body = policy(automatic=[entry()])
        check_policy(body)
        assert activated(body, "company", RULE, "company")
        assert not activated(body, "company", RULE, "deferred")

    def test_nothing_is_active_without_an_entry(self):
        assert not activated(policy(), "company", RULE, "company")

    def test_an_entry_for_another_rule_version_does_not_activate_this_one(self):
        """A rule edited after its proof is orphaned (§9.2)."""
        body = policy(automatic=[entry()])
        assert not activated(body, "company", {**RULE, "version": "x"}, "company")

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"rule_id": "absent"}, "absent"),
            ({"rule_version": "2026-09-23"}, "2026-09-23"),
            ({"verdict": "person"}, "person"),
            ({"verdict": "deferred"}, "deferred"),
            ({"activation": "deterministic"}, "deterministic"),
            ({"family": "binding"}, "binding"),
            ({"kind": "fund"}, "fund"),
            ({"proof": proof(n=1000, correct=1000)}, "below the company bar"),
            ({"proof": proof(lower_bound=0.9995)}, "does not reproduce"),
            ({"proof": proof(confidence=0.9)}, "confidence"),
            ({"proof": proof(method="point_estimate")}, "method"),
            (
                {
                    "proof": proof(
                        adversarial={"fixture_sha256": "a" * 64, "violations": 1}
                    )
                },
                "adversarial",
            ),
            ({"proof": proof(cohort={**proof()["cohort"], "files": {}})}, "cohort"),
            ({"proof": proof(approved_by="")}, "approval"),
            ({"proof": proof(correct=3001)}, "sample"),
        ],
    )
    def test_an_activation_that_does_not_hold_is_refused(self, changes, reason):
        with pytest.raises(Conflict, match=reason):
            check_policy(policy(automatic=[entry(**changes)]))

    def test_a_bar_the_document_lowers_below_the_accepted_one_is_refused(self):
        """The document may raise its bar, never lower it (ticket 02, decision 4)."""
        lowered = {**BAR, "min_precision": 0.9}
        with pytest.raises(Conflict, match="accepted"):
            check_policy(policy(bars={"classification": lowered}))

    def test_company_classification_acts_at_95_percent(self):
        """Confidence bands (company-policy.md): 95% acts, at 95% confidence."""
        bar = {**BAR, "min_precision": 0.95}
        body = policy(
            automatic=[entry(proof=proof(n=60, correct=60))],
            bars={"classification": bar},
        )
        check_policy(body)
        assert activated(body, "company", RULE, "company")

    def test_a_company_proof_below_95_percent_is_refused(self):
        bar = {**BAR, "min_precision": 0.95}
        body = policy(
            automatic=[entry(proof=proof(n=60, correct=58))],
            bars={"classification": bar},
        )
        with pytest.raises(Conflict, match="below the company bar"):
            check_policy(body)

    def test_lowering_classification_never_lowers_consolidation(self):
        """Merging two published Company IDs keeps 99.9% (Q10/Q11): it has no
        accepted bar here, so a document may not declare one at all."""
        with pytest.raises(Conflict, match="no accepted bar"):
            check_policy(policy(bars={"classification": BAR, "consolidation": BAR}))

    def test_a_kind_with_no_bar_for_the_family_cannot_activate(self):
        with pytest.raises(Conflict, match="no bar"):
            check_policy(policy(automatic=[entry()], bars={}))

    def test_one_verdict_is_activated_once(self):
        """§10 check 6: no duplicate (kind, family, rule_id, verdict)."""
        with pytest.raises(Conflict, match="twice"):
            check_policy(policy(automatic=[entry(), entry()]))

    def test_a_legacy_string_entry_is_refused(self):
        with pytest.raises(Conflict, match="entry"):
            check_policy(policy(automatic=["exact"]))


CIK_RULE = {
    "rule_id": "company-cik",
    "version": "2026-09-24",
    "family": "binding",
    "applies_to_verdict": "company",
    "emits": ["bind"],
    "on_no_match": "mint",
    "source": "sec.submissions.company.v1",
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "cik"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "cik"}},
    ],
}
CIK_CONTRACT = {
    "authority": "SEC/EDGAR",
    "sources": ["sec.submissions.company.v1"],
    "normalizer": "normalize_identifier@sec-cik-v1",
    "claim": {"forward": 1, "reverse": None},
    "compatibility": {"field": "kind", "predicate": "kind_equal@1"},
    "verification": {
        "corpus_sha256": "c" * 64,
        "approved_by": "operator",
        "approved_at": "2026-09-24T12:00:00Z",
        "reason": "fixture verification: shape only, not a measurement",
    },
    "tolerance": {"unit": "items", "warm_up_decisions": 10000, "max_per_10k": 5},
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
                "activation": "deterministic",
            }
        ]
    return body


class TestAnIdentifierRule:
    """Ticket 04: identifier-only binding activates on a verified contract."""

    def test_a_verified_contract_activates_the_rule(self):
        body = binding_policy()
        check_policy(body)
        assert activated(body, "company", CIK_RULE, "bind")

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"on_no_match": "guess"}, "on_no_match"),
            ({"emits": ["bind", "consolidate"]}, "exactly bind"),
            ({"applies_to_verdict": "person"}, "sits in kind company"),
            (
                {"when": [{"primitive": "token_match@1", "args": {}}]},
                "not a binding test",
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

    def test_a_rule_that_creates_companies_needs_its_kinds_contract(self):
        rule = {**CIK_RULE, "source": "gleif.level1.v1"}
        with pytest.raises(Conflict, match="no Identifier Contract"):
            check_policy(binding_policy(rule=rule, contract=False, activate=False))

    def test_a_rule_that_only_joins_may_come_from_any_source(self):
        rule = {**CIK_RULE, "on_no_match": "wait", "source": "gleif.level1.v1"}
        check_policy(binding_policy(rule=rule, activate=False))

    def test_no_contract_means_no_activation(self):
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
            ({"verification": {"corpus_sha256": "short"}}, "not verified"),
            ({"tolerance": {"unit": "items"}}, "tolerance"),
        ],
    )
    def test_an_incomplete_contract_is_refused(self, changes, reason):
        with pytest.raises(Conflict, match=reason):
            check_policy(binding_policy(contract={**CIK_CONTRACT, **changes}))

    def test_a_deterministic_activation_of_a_classification_rule_is_refused(self):
        body = policy(
            automatic=[entry(activation="deterministic", family="classification")]
        )
        with pytest.raises(Conflict, match="applies to binding rules"):
            check_policy(body)

    def test_a_binding_rule_cannot_be_measured_into_activity_here(self):
        body = binding_policy(activate=False)
        body["automatic_rules"] = [
            {
                "kind": "company",
                "family": "binding",
                "rule_id": "company-cik",
                "rule_version": "2026-09-24",
                "verdict": "bind",
                "activation": "measured",
                "proof": proof(),
            }
        ]
        with pytest.raises(
            Conflict,
            match="applies to classification and name_binding rules, not binding",
        ):
            check_policy(body)


class TestTheCompanyPolicy:
    """Ticket 12: the approved Account hold-back acts alone."""

    def test_the_approved_rule_activates_only_its_company_verdict(self):
        check_policy(POLICY)
        (rule,) = [
            r
            for r in POLICY["kinds"]["company"]["rules"]
            if r["rule_id"] == "sec-company-candidate"
        ]
        assert activated(POLICY, "company", rule, "company")
        assert not activated(POLICY, "company", rule, "deferred")
        assert all(
            step["lower_bound"] >= 0.95 for step in PROOF["cohort"]["by_step"].values()
        )
        assert PROOF["adversarial"]["violations"] == 0
        assert PROOF["approved_at"] == "2026-09-25T17:09:33Z"
        assert PROOF["approved_by"] == "operator"
        assert POLICY["automatic_rules"] == [APPROVED_ACTIVATION]
        assert APPROVED_ACTIVATION["proof"] is PROOF
        pending = copy.deepcopy(POLICY)
        pending["automatic_rules"] = []
        assert digest(pending) == (
            "31fdbef91859cd8f7423a827ae29156c190b013cff14cde184f3585a2c56f63f"
        )

    def test_the_policy_is_the_active_digest(self):
        assert digest(POLICY) == (
            "35250dad7c22fe9404abda7af8b6be91fb5cfba43859aa531fcc18e2e0111321"
        )

    def test_the_proof_files_match_the_pinned_hashes(self):
        root = Path(__file__).parents[2] / ".scratch/company-mastering/research"
        for name, expected in PROOF["cohort"]["files"].items():
            assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
        summary = json.loads((root / "12-13-summary.json").read_text())
        assert summary["files"] == PROOF["cohort"]["files"]
        assert summary["by_step"] == PROOF["cohort"]["by_step"]
        assert (
            summary["adversarial"]["violations"] == PROOF["adversarial"]["violations"]
        )

    def test_the_account_hold_back_re_scores_from_frozen_labels(self):
        root = Path(__file__).parents[2] / ".scratch/company-mastering/research"
        block = POLICY["kinds"]["company"]
        (rule,) = [r for r in block["rules"] if r["rule_id"] == "sec-company-candidate"]

        def rows(name):
            return [json.loads(line) for line in (root / name).read_text().splitlines()]

        sample = rows("12-13-sample.jsonl")
        adversarial = rows("12-13-adversarial.jsonl")
        held = rows("12-13-held.jsonl")
        for record in sample + adversarial + held:
            verdict, step = fired(
                rule,
                {
                    "entity_type": record["entity_type"],
                    "sic": record["sic"],
                    "category": record["category"],
                    "entity_name": record["name"],
                    "tickers": record["catalog_tickers"],
                    "forms": record["forms"],
                },
                block,
            )
            assert (verdict, step) == (
                "deferred" if record in held else "company",
                record["step"],
            )
            assert record["final"] in {"company", "fund"}

        assert len(sample) == PROOF["n"] == 600
        correct = sum(record["final"] == "company" for record in sample)
        assert correct == PROOF["correct"]
        assert math.isclose(
            wilson_lower_bound(correct, len(sample), 0.95),
            PROOF["lower_bound"],
            abs_tol=1e-6,
        )
        for step, measured in PROOF["cohort"]["by_step"].items():
            group = [record for record in sample if record["step"] == step]
            step_correct = sum(record["final"] == "company" for record in group)
            assert (len(group), step_correct) == (measured["n"], measured["correct"])
            assert math.isclose(
                wilson_lower_bound(step_correct, len(group), 0.95),
                measured["lower_bound"],
                abs_tol=1e-6,
            )
        assert len(adversarial) == PROOF["adversarial"]["n"]
        assert (
            sum(record["final"] != "company" for record in adversarial)
            == (PROOF["adversarial"]["violations"])
        )


COMPANY_BAR = {**BAR, "min_precision": 0.95}


class TestEachStepClearsTheBar:
    """The bar is per rule step, not per pooled sample (`company-policy.md`)."""

    def test_a_failing_step_cannot_hide_behind_a_passing_one(self):
        body = proof(n=600, correct=582)
        # Pooled 582/600 clears 0.95; step 4 alone (282/300) does not.
        body["cohort"]["by_step"]["4"] = {
            "n": 300,
            "correct": 282,
            "lower_bound": math.floor(wilson_lower_bound(282, 300, 0.95) * 1e6) / 1e6,
        }
        with pytest.raises(Conflict, match="Proof step 4 lower bound .* below"):
            _check_proof("company", COMPANY_BAR, body, ["2", "4"])

    def test_a_step_with_no_sample_of_its_own_is_refused(self):
        body = proof()
        del body["cohort"]["by_step"]["4"]
        with pytest.raises(Conflict, match="no sample of its own for step 4"):
            _check_proof("company", COMPANY_BAR, body, ["2", "4"])

    def test_the_measured_sec_rule_clears_the_bar_at_every_company_step(self):
        approved = {**PROOF, "approved_by": "x", "approved_at": "y"}
        _check_proof("company", COMPANY_BAR, approved, ["8", "10"])


def _name_rules():
    import json as _json
    from pathlib import Path as _Path

    frozen = _json.loads(
        (
            _Path(__file__).resolve().parents[2]
            / ".scratch/company-mastering/research/08-rules.json"
        ).read_text()
    )["rules"]
    return {(r["rule_id"], r["version"]): r for r in frozen}


NAME_RULES = _name_rules()
NAME_STATE = NAME_RULES[("sec-gleif-name-jurisdiction", "2026-09-25.1")]
NAME_POSTCODE = NAME_RULES[("sec-gleif-name-postal", "2026-09-25.2")]


def name_policy(rule=None, activate=True, bar=True):
    rule = rule or NAME_STATE
    body = policy(
        rules=[RULE, rule],
        bars={"classification": BAR, **({"name_binding": COMPANY_BAR} if bar else {})},
    )
    if activate:
        body["automatic_rules"] = [
            {
                "kind": "company",
                "family": "name_binding",
                "rule_id": rule["rule_id"],
                "rule_version": rule["version"],
                "verdict": "bind",
                "activation": "measured",
                "proof": proof(n=300, correct=300),
            }
        ]
    return body


class TestANameBindingRule:
    """Ticket 08: the SEC-to-GLEIF matching rules activate by measurement."""

    @pytest.mark.parametrize("rule", [NAME_STATE, NAME_POSTCODE])
    def test_the_frozen_rules_are_well_formed_and_activate_at_95(self, rule):
        body = name_policy(rule)
        check_policy(body)
        assert activated(body, "company", rule, "bind")

    def test_a_bar_below_95_is_refused(self):
        body = name_policy()
        body["kinds"]["company"]["bars"]["name_binding"] = {
            **COMPANY_BAR,
            "min_precision": 0.9,
        }
        with pytest.raises(Conflict, match="below the accepted"):
            check_policy(body)

    def test_a_proof_below_the_bar_is_refused(self):
        body = name_policy()
        body["automatic_rules"][0]["proof"] = proof(n=100, correct=94)
        with pytest.raises(Conflict, match="below the company bar"):
            check_policy(body)

    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"on_no_match": "mint"}, "never creates a Company"),
            ({"emits": ["bind", "review"]}, "exactly bind"),
            ({"holder_source": None}, "holds the Company"),
            (
                {"when": [{"primitive": "name_census_match@1", "args": {}}]},
                "never the name alone",
            ),
            (
                {"when": [{"primitive": "identifier_match@1", "args": {}}]},
                "not a name binding test",
            ),
        ],
    )
    def test_a_malformed_rule_is_refused(self, changes, reason):
        with pytest.raises(Conflict, match=reason):
            check_policy(name_policy({**NAME_STATE, **changes}, activate=False))

    def test_a_kind_verdict_cannot_be_measured_for_a_name_binding(self):
        body = name_policy()
        body["automatic_rules"][0]["verdict"] = "company"
        with pytest.raises(Conflict, match="does not emit|cannot prove"):
            check_policy(body)

    def test_identifier_binding_still_activates_only_deterministically(self):
        body = binding_policy()
        body["automatic_rules"][0]["activation"] = "measured"
        body["automatic_rules"][0]["proof"] = proof()
        with pytest.raises(Conflict, match="applies to"):
            check_policy(body)
