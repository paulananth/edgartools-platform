"""Real PG16: SEC-to-GLEIF name matching in the Merge Stage (ticket 08).

A waiting GLEIF record joins the Company its SEC record holds by CIK when the
Name Census names exactly this CIK and this LEI, both name keys agree with the
legal form kept, and the place test holds. Either source may load first.

The activations are **fixture** activations with arithmetic-only proofs.
Nothing in the production policy activates a matching rule before the
operator approves its digest.
"""

from __future__ import annotations

import copy
from uuid import uuid4

from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.name_census import VERSION as CENSUS
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.mdm.test_clean_activation import (
    BAR,
    CIK_CONTRACT,
    CIK_RULE,
    COMPANY_BAR,
    NAME_POSTCODE,
    NAME_STATE,
    proof,
)

postgres = core.postgres
database = core.database

# The Stage registers the fixture datasets: fixture.primary stands for SEC
# (it issues CIKs), fixture.secondary for GLEIF (it issues LEIs).
SEC = "fixture.primary"
GLEIF = "fixture.secondary"
CIK_MINT = {**CIK_RULE, "source": SEC}
CIK_ISSUED = {**CIK_CONTRACT, "sources": [SEC]}
STATE_RULE = {**NAME_STATE, "source": GLEIF, "holder_source": SEC}
POSTCODE_RULE = {**NAME_POSTCODE, "source": GLEIF, "holder_source": SEC}
APPLE_CIK, APPLE_LEI = "0000320193", "HWUPKR0MPOU8FGXBT394"
UPDATED = "2026-09-01T00:00:00Z"
LEI_WAIT = {
    **{k: v for k, v in CIK_RULE.items() if k != "source"},
    "rule_id": "company-lei",
    "on_no_match": "wait",
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "lei"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "lei"}},
    ],
}
LEI_CONTRACT = {
    **CIK_CONTRACT,
    "authority": "GLEIF",
    "sources": [GLEIF],
    "normalizer": "normalize_identifier@lei-v1",
}


def name_policy(database, *, names=(STATE_RULE, POSTCODE_RULE), active=True):
    body = {
        "version": "name-matching-test",
        "required_consumers": ["export", "graph"],
        "automatic_rules": [],
        "kinds": {
            "company": {
                "version": "company-test",
                "defaults": {"sources": [SEC, GLEIF], "allow_unknown_effective": True},
                "rules": [CIK_MINT, LEI_WAIT, *names],
                "identifiers": {"cik": CIK_ISSUED, "lei": LEI_CONTRACT},
                "bars": {"classification": BAR, "name_binding": COMPANY_BAR},
            }
        },
    }
    body["automatic_rules"] = [
        {
            "kind": "company",
            "family": "binding",
            "rule_id": r["rule_id"],
            "rule_version": r["version"],
            "verdict": "bind",
            "activation": "deterministic",
        }
        for r in (CIK_MINT, LEI_WAIT)
    ]
    if active:
        body["automatic_rules"] += [
            {
                "kind": "company",
                "family": "name_binding",
                "rule_id": r["rule_id"],
                "rule_version": r["version"],
                "verdict": "bind",
                "activation": "measured",
                "proof": proof(n=300, correct=300),
            }
            for r in names
        ]
    with database.admin.begin() as conn:
        return register_policy(conn, copy.deepcopy(body))


def census(key="APPLE INC", ciks=(APPLE_CIK,), leis=((APPLE_LEI, UPDATED),), other=0):
    return {
        "census": "c" * 64,
        "version": CENSUS,
        "key": key,
        "ciks": list(ciks),
        "cik_count": len(ciks),
        "leis": [list(pair) for pair in leis],
        "lei_count": len(leis),
        "other_name_holders": other,
    }


def sec(
    cik=APPLE_CIK,
    name="APPLE INC",
    state="CA",
    postal="95014",
    country="US",
    entry=None,
):
    return core.source(
        key=cik,
        source_code=SEC,
        fields={"name": name, "state_of_incorporation": state},
        identifiers={"cik": cik},
        provenance={
            "matching": {
                "business_postal_code": postal,
                "business_country": country,
                "name_census": census() if entry is None else entry,
            }
        },
    )


def gleif(
    lei=APPLE_LEI,
    name="Apple Inc.",
    jurisdiction="US-CA",
    updated=UPDATED,
    status="ACTIVE",
    postal="95014",
    country="US",
):
    return core.source(
        key=lei,
        source_code=GLEIF,
        fields={
            "name": name,
            "jurisdiction": jurisdiction,
            "gleif_last_update": updated,
            "gleif_entity_status": status,
            "gleif_registration_status": "ISSUED",
        },
        identifiers={"lei": lei},
        provenance={
            "matching": {
                "headquarters_postal_code": postal,
                "headquarters_country": country,
            }
        },
    )


def load(database, policy, batch, *assertions, checkpoint=1):
    return MergeStage(Store(database.application)).apply(
        batch_id=batch,
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="load",
        expected_checkpoint=checkpoint - 1,
        checkpoint=checkpoint,
        as_of=core.AS_OF,
        assertions=list(assertions),
    )


def companies(database):
    return [
        v for v in core.documents(database, "entity").values() if v["kind"] == "company"
    ]


def test_a_gleif_record_joins_the_company_its_sec_record_holds(database):
    policy = name_policy(database)
    load(database, policy, "sec", sec())
    load(database, policy, "gleif", gleif(), checkpoint=2)
    (only,) = companies(database)
    assert only["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}


def test_a_waiting_gleif_record_joins_when_its_sec_record_arrives(database):
    policy = name_policy(database)
    load(database, policy, "gleif", gleif())
    assert companies(database) == []
    load(database, policy, "sec", sec(), checkpoint=2)
    (only,) = companies(database)
    assert only["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}


def test_both_records_in_one_batch_make_one_company(database):
    policy = name_policy(database)
    load(database, policy, "both", sec(), gleif())
    (only,) = companies(database)
    assert only["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}


def _waits(database, policy, sec_record, gleif_record):
    load(database, policy, "sec", sec_record)
    load(database, policy, "gleif", gleif_record, checkpoint=2)
    (only,) = companies(database)
    assert only["identifiers"] == {"cik": [sec_record["record_key"]]}


def test_a_name_the_census_gives_two_leis_waits(database):
    two = census(leis=((APPLE_LEI, UPDATED), ("549300OTHER000000001", UPDATED)))
    _waits(database, name_policy(database), sec(entry=two), gleif())


def test_a_name_another_sec_filer_carried_waits(database):
    _waits(
        database,
        name_policy(database),
        sec(entry=census(ciks=(APPLE_CIK, "0000000002"))),
        gleif(),
    )


def test_a_gleif_record_updated_since_the_census_waits(database):
    _waits(
        database, name_policy(database), sec(), gleif(updated="2026-09-20T00:00:00Z")
    )


def test_a_different_legal_form_waits(database):
    _waits(database, name_policy(database), sec(), gleif(name="Apple LLC"))


def test_an_inactive_gleif_entity_waits(database):
    _waits(database, name_policy(database), sec(), gleif(status="INACTIVE"))


def test_neither_place_agreeing_waits(database):
    _waits(
        database,
        name_policy(database),
        sec(state="CA"),
        gleif(jurisdiction="US-NV", postal="89501", country="US"),
    )


def test_the_postcode_rule_vetoes_two_places_of_incorporation(database):
    # AAON, Inc.: a Nevada parent and its Oklahoma subsidiary share an address.
    _waits(
        database,
        name_policy(database),
        sec(state="NV", postal="74107"),
        gleif(jurisdiction="US-OK", postal="74107"),
    )


def test_the_postcode_rule_sets_aside_a_us_state_both_other_sources_contradict(
    database,
):
    # Shell: SEC's state reads DC; its business address and GLEIF say Britain.
    policy = name_policy(database)
    shell = census(
        key="SHELL PLC", ciks=("0001306965",), leis=(("21380068P1DRHMJ8KU70", UPDATED),)
    )
    load(
        database,
        policy,
        "sec",
        sec(
            cik="0001306965",
            name="Shell plc",
            state="DC",
            postal="SE1 7NA",
            country="GB",
            entry=shell,
        ),
    )
    load(
        database,
        policy,
        "gleif",
        gleif(
            lei="21380068P1DRHMJ8KU70",
            name="Shell plc",
            jurisdiction="GB",
            postal="SE1 7NA",
            country="GB",
        ),
        checkpoint=2,
    )
    (only,) = companies(database)
    assert only["identifiers"] == {
        "cik": ["0001306965"],
        "lei": ["21380068P1DRHMJ8KU70"],
    }


def test_an_inactive_rule_proposes_nothing(database):
    _waits(database, name_policy(database, active=False), sec(), gleif())


def test_a_company_that_holds_another_lei_waits(database):
    policy = name_policy(database)
    load(database, policy, "sec", sec())
    load(database, policy, "gleif", gleif(), checkpoint=2)
    other = gleif(lei="549300OTHER000000001")
    load(database, policy, "gleif-2", other, checkpoint=3)
    (only,) = companies(database)
    assert only["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}
