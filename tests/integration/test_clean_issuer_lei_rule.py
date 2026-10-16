"""Real PG16: the issuer LEI rule (tickets 22 and 97).

A GLEIF record an N-PORT holding names as its issuer (`matching.nport_issuer`)
joins the one Company holding its LEI, or creates it; any other GLEIF record
still waits for the SEC-GLEIF name rules. The rule is switched on here only, in
a copy of the repo's policy.
"""

from __future__ import annotations

import copy

from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_cik_rule import GLEIF, companies, load, operations, register

postgres = core.postgres
database = core.database

ISSUER, OTHER = "5493001KJTIIGC8Y1R12", "HWUPKR0MPOU8FGXBT394"
RULE = "gleif-issuer-lei"


def switched_on() -> dict:
    body = copy.deepcopy(files.policy())
    company = body["kinds"]["company"]
    company["identifiers"]["lei"]["verification"] = {
        "corpus_sha256": "0" * 64, "approved_by": "test", "approved_at": core.AS_OF, "reason": "test only"}
    rule = next(r for r in company["rules"] if r["rule_id"] == RULE)
    body["automatic_rules"].append({"kind": "company", "family": "binding", "rule_id": RULE,
                                    "rule_version": rule["version"], "verdict": "bind",
                                    "activation": "deterministic"})
    return body


def gleif(lei, issuer, key=None, revision=1):
    matching = {"nport_issuer": True} if issuer else {}
    return core.source(key=key or lei, source_code=GLEIF, revision=revision, fields={"name": f"Entity {lei[-4:]}"},
                       identifiers={"lei": lei}, provenance={"matching": matching})


def test_an_issuer_record_creates_its_company_and_another_gleif_record_waits(database):
    policy = register(database, switched_on())
    load(database, policy, "b1", gleif(ISSUER, issuer=True), gleif(OTHER, issuer=False))
    (made,) = companies(database).values()
    assert made["identifiers"]["lei"] == [ISSUER]
    assert operations(database) == ["bind"]


def test_a_second_issuer_record_with_that_lei_joins_the_same_company(database):
    policy = register(database, switched_on())
    load(database, policy, "b1", gleif(ISSUER, issuer=True))
    load(database, policy, "b2", gleif(ISSUER, issuer=True, key="second"), checkpoint=2)
    assert len(companies(database)) == 1
    assert operations(database) == ["bind", "bind"]


def test_switched_off_the_rule_creates_nothing(database):
    policy = register(database, files.policy())
    load(database, policy, "b1", gleif(ISSUER, issuer=True))
    assert companies(database) == {}
