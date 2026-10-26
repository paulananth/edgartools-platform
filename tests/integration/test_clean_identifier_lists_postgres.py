"""Real PG16: a record carrying a list of one identifier kind (ticket 138).

An OpenFIGI answer carries a FIGI for each listing. The record creates one
Security holding every value; a later record carrying any one of them joins
it; two records in one batch sharing a value make one Security; and the
Security, whose contract sets no reverse limit, is accepted, not reviewed.
The CIK namespace stands in for any identifier; values are invented.
"""

from __future__ import annotations

import copy

from sqlalchemy import event, text

from edgar_warehouse.context import Context
from edgar_warehouse.mdm.clean import binding
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


def list_policy_body(database):
    """The registered body itself, for the readers that take the policy."""
    digest = list_policy(database)
    with database.admin.connect() as conn:
        return digest, conn.execute(text(
            "SELECT body FROM mdm.policy WHERE digest = :d"), {"d": digest}).scalar()


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


def test_a_value_held_by_the_security_it_was_proposed_for_is_not_stale(database):
    policy, body = list_policy_body(database)
    load(database, policy, "b1", security("answer", FIRST, SECOND))
    (master,) = masters(database)
    proposal = {"joins": [], "identities": [],
                "mints": [{"entity_id": master, "namespace": "cik", "raw": SECOND}]}
    with database.application.connect() as conn:
        assert not binding.proposal_is_stale(conn, body, proposal)
        proposal["mints"][0]["entity_id"] = "00000000-0000-0000-0000-00000000000b"
        assert binding.proposal_is_stale(conn, body, proposal)


def _seeded(database, policy):
    """A cohort large enough that a whole-index read would show."""
    for batch in range(4):
        items = [security(f"cohort-{batch}-{n}", f"{batch}{n:09d}", f"{batch + 5}{n:09d}")
                 for n in range(500)]
        load(database, policy, f"cohort-{batch}", *items, checkpoint=batch + 1)
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE mdm.stage_record"))


def _plan(conn, statement, params):
    plan = conn.exec_driver_sql("EXPLAIN (ANALYZE,FORMAT JSON) " + statement, params).scalar()

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)
    return list(nodes(plan[0]["Plan"]))


def _captured(conn, marker, call):
    statements = []

    def capture(conn, cursor, statement, params, context, many):
        if marker in statement:
            statements.append((statement, params))
    event.listen(conn, "before_cursor_execute", capture)
    try:
        result = call()
    finally:
        event.remove(conn, "before_cursor_execute", capture)
    return result, statements[-1]


def test_each_value_is_one_probe_of_the_identifier_index(database):
    policy, body = list_policy_body(database)
    _seeded(database, policy)
    # One value carried alone, one inside a list: two probes per value.
    wanted = {"cik": {"0000000007", "5000000009"}}
    with database.application.connect() as conn:
        found, (statement, params) = _captured(
            conn, "unnest(CAST(%(wanted)s", lambda: binding.holders(conn, body, wanted))
        assert {value for _, value in found} == {"7", "5000000009"}  # normalized
        nodes = _plan(conn, statement, params)
    probes = [n for n in nodes if n.get("Index Name") == "stage_record_identifiers"]
    assert len(probes) == 1 and probes[0]["Actual Loops"] == 4
    assert not any(n["Node Type"] == "Seq Scan" and n.get("Relation Name") == "stage_record"
                   for n in nodes)


def test_the_agent_lookup_finds_a_value_in_a_list_by_one_index_probe_each(database):
    policy, _ = list_policy_body(database)
    _seeded(database, policy)
    context = Context(database.application)
    with database.application.connect() as conn:
        entity, (statement, params) = _captured(
            conn, "unnest(CAST(%(docs)s", lambda: context._resolve(conn, "security", "cik:5000000009"))
        nodes = _plan(conn, statement, params)
    assert entity in masters(database)
    probes = [n for n in nodes if n.get("Index Name") == "stage_record_identifiers"]
    assert len(probes) == 1 and probes[0]["Actual Loops"] == 2
    assert not any(n["Node Type"] == "Seq Scan" and n.get("Relation Name") == "stage_record"
                   for n in nodes)


def test_the_values_a_bind_withholds_are_read_by_one_probe_of_the_subject_index_each(database):
    """Ticket 138 part A2b: each record's live bind is read by its subject, one index probe each."""
    policy, _ = list_policy_body(database)
    _seeded(database, policy)
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE mdm.decision"))
        subjects = [r[0] for r in conn.execute(text(
            "SELECT body->>'subject' FROM mdm.decision WHERE operation = 'bind' LIMIT 3"))]
    with database.application.connect() as conn:
        found, (statement, params) = _captured(
            conn, "operation IN ('bind', 'revoke')", lambda: binding.withheld(conn, set(subjects)))
        assert found == {}  # these binds withhold nothing
        nodes = _plan(conn, statement, params)
    probes = [n for n in nodes if n.get("Index Name") == "decision_subject"]
    assert len(probes) == 1 and probes[0]["Actual Loops"] == 3
    assert not any(n["Node Type"] == "Seq Scan" and n.get("Relation Name") == "decision" for n in nodes)
