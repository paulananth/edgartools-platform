"""Ticket 07: three Clean MDM behaviours the ADV design depends on (no database).

    uv run --no-sync python .scratch/profiling/trials/readers/custody-13m/engine_checks.py
"""
from types import SimpleNamespace

from edgar_warehouse.mdm.clean import relationships, survivorship
from edgar_warehouse.mdm.clean.evidence import assertion


def a(pub, fields, effective_at=None, rels=None, key="r1"):
    return assertion(source_code="adv.t.v1", record_key=key, publication_key=pub, revision=1,
                     effective_at=effective_at, kind="company", fields=fields, relationships=rels)


def run(name, fn):
    try:
        print(f"{name}: {fn()}")
    except Exception as exc:  # noqa: BLE001 - the outcome is the finding
        print(f"{name}: {type(exc).__name__}: {exc}")


NOW = "2026-10-09T00:00:00+00:00"
# 1. One record restated by a second publication, both revision 1 (what mdm.prepare writes).
run("1a restated, different fields", lambda: list(survivorship.current_claims(
    [a("p1", {"legal_name": "A"}), a("p2", {"legal_name": "B"})], NOW, set())))
run("1b restated, identical fields", lambda: list(survivorship.current_claims(
    [a("p1", {"legal_name": "A"}), a("p2", {"legal_name": "A"})], NOW, set())))

# 2 and 3. Links projected between two accepted companies.
ents = {"E1": {"kind": "company", "status": "accepted", "profiles": []},
        "E2": {"kind": "company", "status": "accepted", "profiles": []}}
state = SimpleNamespace(bindings={"S": "E1", "T": "E2"}, canonical={"E1": "E1", "E2": "E2"})
types = {"CUSTODIAN": {"from": ["company"], "to": ["company"]}}


def project(links):
    claims = {f"L{i}": {"assertion_id": f"x{i}", "relationships": [l], "source_meta": {"effective_at": eff}}
              for i, (l, eff) in enumerate(links)}
    edges, reviews = relationships.project(claims, state, ents, NOW, types=types)
    return {"edges": [{"periods": [(p.get("valid_from"), p.get("valid_to")) for p in e["periods"]], "last_seen": e["last_seen"]} for e in edges],
            "reviews": sorted({r["reason"] for r in reviews})}


link = {"type": "CUSTODIAN", "source_subject": "S", "target_subject": "T", "scope": "t"}
run("2 undated link, no effective time", lambda: project([(link, None)]))
run("3a two filings, stated open periods", lambda: project(
    [({**link, "valid_from": "2025-06-24T00:00:00+00:00"}, None), ({**link, "valid_from": "2026-03-10T00:00:00+00:00"}, None)]))
run("3b two filings, observed (publication time)", lambda: project(
    [(link, "2025-06-30T00:00:00+00:00"), (link, "2026-03-31T00:00:00+00:00")]))
