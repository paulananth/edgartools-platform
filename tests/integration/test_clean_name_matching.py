"""Shared fixture builders; retired calculation tests are catalogued in ticket 08."""

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
            "gleif_entity_status": status,
            "gleif_registration_status": "ISSUED",
        },
        identifiers={"lei": lei},
        # GLEIF's LastUpdateDate is the record's effective time (ticket 129).
        effective_at=updated,
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


def _waits(database, policy, sec_record, gleif_record):
    load(database, policy, "sec", sec_record)
    load(database, policy, "gleif", gleif_record, checkpoint=2)
    (only,) = companies(database)
    assert only["identifiers"] == {"cik": [sec_record["record_key"]]}
