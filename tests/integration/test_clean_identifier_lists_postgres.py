"""Real PG16: a record carrying a list of one identifier kind (ticket 138).

An OpenFIGI answer carries a FIGI for each listing. The record creates one
Security holding every value; a later record carrying any one of them joins
it; two records in one batch sharing a value make one Security; and the
Security, whose contract sets no reverse limit, is accepted, not reviewed.
The CIK namespace stands in for any identifier; values are invented.
"""

from __future__ import annotations

import copy

from edgar_warehouse.mdm.clean.store import register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_identifier_binding import CIK_ISSUED, CIK_MINT, load

FIRST, SECOND, THIRD = "0000000017", "0000000018", "0000000019"


def list_policy(database):
    rule = {**CIK_MINT, "applies_to_verdict": "security"}
    body = {
        "version": "identifier-list-test",
        "required_consumers": ["export", "graph"],
        "automatic_rules": [{
            "kind": "security", "family": "binding", "rule_id": rule["rule_id"],
            "rule_version": rule["version"], "verdict": "bind", "activation": "deterministic",
        }],
        "kinds": {"security": {
            "version": "security-test",
            "defaults": {"sources": ["fixture.primary"], "allow_unknown_effective": True},
            "rules": [rule],
            "identifiers": {"cik": {**CIK_ISSUED, "claim": {"forward": 1, "reverse": None}}},
        }},
    }
    with database.admin.begin() as conn:
        return register_policy(conn, copy.deepcopy(body))


def security(key, *values):
    return core.source(key=key, kind="security", fields={"name": f"Security {key}"},
                       identifiers={"cik": list(values) if len(values) > 1 else values[0]})


def masters(database):
    return {k: v for k, v in core.documents(database, "entity").items() if v["kind"] == "security"}


def test_a_list_creates_one_security_and_a_later_record_joins_by_any_value(database):
    policy = list_policy(database)
    load(database, policy, "b1", security("answer", FIRST, SECOND))
    load(database, policy, "b2", security("holding", SECOND), checkpoint=2)
    (only,) = masters(database).values()
    assert only["status"] == "accepted" and only["identifiers"] == {"cik": [FIRST, SECOND]}
    assert len(only["subjects"]) == 2


def test_two_records_in_one_batch_sharing_a_value_make_one_security(database):
    policy = list_policy(database)
    load(database, policy, "b1", security("left", FIRST, SECOND), security("right", SECOND, THIRD))
    (only,) = masters(database).values()
    assert only["status"] == "accepted" and only["identifiers"] == {"cik": [FIRST, SECOND, THIRD]}


def test_records_sharing_no_value_make_two_securities(database):
    policy = list_policy(database)
    load(database, policy, "b1", security("left", FIRST), security("right", SECOND, THIRD))
    assert sorted(m["identifiers"]["cik"] for m in masters(database).values()) == [
        [FIRST], [SECOND, THIRD]]
