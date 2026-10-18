"""Real PG16: the issuer LEI rule (tickets 22 and 97).

A GLEIF record an N-PORT holding names as its issuer (`matching.nport_issuer`)
joins the one Company holding its LEI, and otherwise waits for the SEC-GLEIF
name rules; it never creates a Company (operator, 2026-10-16: "Wait, config
only"). That a record an identifier rule leaves waiting still reaches the name
rules in its batch is `test_clean_name_matching.py`'s
`test_a_gleif_record_joins_the_company_its_sec_record_holds`. The rules are
switched on here only, in a copy of the repo's policy.
"""

from __future__ import annotations

from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_clean_cik_rule as cik
from tests.integration.test_clean_cik_rule import GLEIF, companies, load, operations
from tests.mdm import policy_layers


ISSUER, OTHER = "9999000000EXAMPLE113", "9999000000EXAMPLE210"  # invented; check digits hold
RULE = "gleif-issuer-lei"
ADV = "iapd.adv.custodians.v1"


def switched_on() -> dict:
    """The issuer rule; the ADV custodian rule that gives a Company an LEI to
    join is on in the live policy (ticket 76)."""
    return policy_layers.with_rules_on(files.policy(), "company", RULE)


def register(database, body) -> str:
    core.register_reading(database, ADV, core.contract_body())
    return cik.register(database, body)


def custodian(lei):
    return core.source(key=f"custodian-{lei}", source_code=ADV, fields={"name": f"Custodian {lei[-4:]}"},
                       identifiers={"lei": lei})


def gleif(lei, issuer, key=None, revision=1):
    matching = {"nport_issuer": True} if issuer else {}
    return core.source(key=key or lei, source_code=GLEIF, revision=revision, fields={"name": f"Entity {lei[-4:]}"},
                       identifiers={"lei": lei}, provenance={"matching": matching})


def test_an_issuer_record_no_company_holds_waits_and_creates_nothing(database):
    policy = register(database, switched_on())
    load(database, policy, "b1", gleif(ISSUER, issuer=True), gleif(OTHER, issuer=False))
    assert companies(database) == {}
    assert operations(database) == []


def test_an_issuer_record_joins_the_one_company_holding_its_lei(database):
    policy = register(database, switched_on())
    load(database, policy, "b1", custodian(ISSUER))
    load(database, policy, "b2", gleif(ISSUER, issuer=True), gleif(OTHER, issuer=False), checkpoint=2)
    (made,) = companies(database).values()
    assert made["identifiers"]["lei"] == [ISSUER]
    assert operations(database) == ["bind", "bind"]


def test_switched_off_the_rule_creates_nothing(database):
    policy = register(database, files.policy())
    load(database, policy, "b1", gleif(ISSUER, issuer=True))
    assert companies(database) == {}
