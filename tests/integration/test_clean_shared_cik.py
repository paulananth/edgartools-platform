"""Real PG16: two kinds that each read SEC's CIK (platform validation 05a).

SEC gives a CIK to a Company or a Person, never both. Once a second kind
declares its own CIK Identifier Contract, the Merge Stage looks a CIK up across
both kinds' issuers: a Person's CIK finds the Person it already made, and a CIK
a Company holds sends a Person record to review instead of making a Person.

The activations are **fixture** activations, as in
`test_clean_identifier_binding.py`.
"""

from __future__ import annotations

import copy

from edgar_warehouse.mdm.clean.store import register_policy
from tests.support.rules_authority import register_dataset
from tests.integration import test_clean_identifier_binding as binding
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database

CIK = binding.APPLE_CIK
PERSON_CIK = {**binding.CIK_RULE, "rule_id": "person-cik", "source": "fixture.person",
              "applies_to_verdict": "person"}


def two_kinds() -> dict:
    return {
        "version": "shared-cik-test",
        "required_consumers": ["export", "graph"],
        "kinds": {
            "company": {
                "version": "company-test",
                "defaults": {"sources": ["fixture.primary"], "allow_unknown_effective": True},
                "rules": [binding.CIK_MINT],
                "identifiers": {"cik": binding.CIK_ISSUED},
            },
            "person": {
                "version": "person-test",
                "defaults": {"sources": ["fixture.person"], "allow_unknown_effective": True},
                "rules": [PERSON_CIK],
                "identifiers": {"cik": {**binding.CIK_CONTRACT, "sources": ["fixture.person"]}},
            },
        },
        "automatic_rules": [
            {"kind": kind, "family": "binding", "rule_id": rule["rule_id"],
             "rule_version": rule["version"], "verdict": "bind", "activation": "deterministic"}
            for kind, rule in (("company", binding.CIK_MINT), ("person", PERSON_CIK))
        ],
    }


def policy(database):
    with database.admin.begin() as conn:
        register_dataset(conn, "fixture.person", database.registry, core.contract_body())
        return register_policy(conn, copy.deepcopy(two_kinds()))


def person(key):
    return core.source(key=key, source_code="fixture.person", kind="person",
                       fields={"name": f"Person {key}"}, identifiers={"cik": CIK})


def entities(database, kind):
    return [v for v in core.documents(database, "entity").values() if v["kind"] == kind]


def test_a_persons_cik_finds_the_person_it_already_made(database):
    digest = policy(database)
    binding.load(database, digest, "b1", person("a"))
    binding.load(database, digest, "b2", person("b"), checkpoint=2)
    (only,) = entities(database, "person")
    assert len(only["subjects"]) == 2


def test_a_cik_a_company_holds_sends_a_person_record_to_review(database):
    digest = policy(database)
    binding.load(database, digest, "b1", binding.record("a", cik=CIK))
    binding.load(database, digest, "b2", person("p"), checkpoint=2)
    assert entities(database, "person") == []
    assert len(entities(database, "company")) == 1
    assert "incompatible_identifier_kind" in {r["reason"] for r in binding.open_reviews(database)}


def test_a_cik_a_person_holds_sends_a_company_record_to_review(database):
    digest = policy(database)
    binding.load(database, digest, "b1", person("p"))
    binding.load(database, digest, "b2", binding.record("a", cik=CIK), checkpoint=2)
    assert entities(database, "company") == []
    assert len(entities(database, "person")) == 1
    assert "incompatible_identifier_kind" in {r["reason"] for r in binding.open_reviews(database)}
