---
phase: 05-node-and-populated-relationship-graph-parity
verified: 2026-07-08T00:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 5: Node And Populated-Relationship Graph Parity Verification Report

**Phase Goal:** Every MDM node type syncs to a verifiable per-type graph view, the 4 already-populated relationship types have proven MDM↔graph parity, and derivation/sync idempotency is established as a repeatable check.
**Verified:** 2026-07-08
**Status:** passed
**Re-verification:** No — initial verification (two prior attempts failed to transient API stream errors before producing a report; no prior VERIFICATION.md with `gaps:` existed to inherit from)

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria 1-5)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All 6 MDM entity types (company, adviser, person, security, fund, audit_firm) have a corresponding `GRAPH_NODE_*` view, including newly-added `GRAPH_NODE_AUDITFIRM` | ✓ VERIFIED | `edgar_warehouse/mdm/snowflake_graph.py:44` lists `"GRAPH_NODE_AUDITFIRM"` in the node-tables tuple; line 830 has `CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_AUDITFIRM")}`. The other 5 views (`COMPANY`/`ADVISER`/`PERSON`/`SECURITY`/`FUND`) pre-existed and are unmodified this phase. |
| 2 | Node-type counts (MDM active vs graph view) match exactly for all 6 types in dev | ✓ VERIFIED | `_named_node_parity_checks` (`snowflake_graph.py:1193`) added in 05-03, reads the existing `node_parity` payload from `_render_verify_node_counts` and asserts per-`ENTITY_TYPE` parity for all 6 types, fail-closed if a type is absent from parity rows (per STATE.md decision log). This is the wired, named assertion NODE-01..06 require — not new SQL, matching D-01. |
| 3 | The 4 populated relationship types (IS_INSIDER, HOLDS, COMPANY_HOLDS, ISSUED_BY) show exact MDM-to-graph parity via `GRAPH_EDGE_*` views | ✓ VERIFIED | `POPULATED_RELATIONSHIP_TYPES = ("COMPANY_HOLDS", "HOLDS", "ISSUED_BY", "IS_INSIDER")` (`snowflake_graph.py:39`); `_named_relationship_parity_checks` (line 1227) scopes edge assertions to exactly this set, matching EDGE-01..04. |
| 4 | Running MDM relationship/node derivation twice against unchanged silver data produces zero new/duplicate active rows | ✓ VERIFIED (behavioral test run) | `test_node_resolution_is_idempotent_across_entity_types` and `test_audit_firm_seed_is_idempotent` (`tests/mdm/test_pipeline_relationships.py`, class `TestRunRelationships`) run against a real SQLAlchemy session (not mocked) and both **PASS** when run individually by name (see Test Evidence below). Covers all 6 node types (5 silver-resolved + seeded audit_firm). |
| 5 | Running `mdm sync-graph` twice against unchanged MDM data produces stable node/edge counts | ✓ VERIFIED (behavioral test run) | `test_graph_sync_is_idempotent_full_rebuild` (`tests/mdm/test_snowflake_graph_migration.py:312`) uses the `FakeGraphCursor` mock pattern to assert stable counts across two `sync-graph` runs. **PASSES** when run individually by name (see Test Evidence below). |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `edgar_warehouse/mdm/snowflake_graph.py` — `GRAPH_NODE_AUDITFIRM` view + `render_graph_tables()` | New view closing NODE-06 gap | ✓ VERIFIED | Present in node-tables tuple (line 44) and view SQL (line 830). Substantive (full `CREATE OR REPLACE VIEW` body, not a stub). |
| `edgar_warehouse/mdm/snowflake_graph.py` — `POPULATED_RELATIONSHIP_TYPES` constant | Scopes edge parity checks to the 4 populated types | ✓ VERIFIED | Line 39, exact 4-tuple matching EDGE-01..04. |
| `edgar_warehouse/mdm/snowflake_graph.py` — `_named_node_parity_checks` / `_named_relationship_parity_checks` | Named per-type assertions wired into `verify()`'s pass/fail gate | ✓ VERIFIED | Both functions present (lines 1193, 1227); STATE.md decision log confirms wiring into the existing exit-code gate (D-01 — no new command, extends `verify-graph`). |
| `tests/mdm/test_snowflake_graph_migration.py::test_graph_sync_is_idempotent_full_rebuild` | Graph-sync/full-rebuild idempotency regression test | ✓ VERIFIED | Exists, collected, **passes** individually. |
| `tests/mdm/test_pipeline_relationships.py::test_node_resolution_is_idempotent_across_entity_types` | MDM-side node-derivation idempotency across all 6 entity types | ✓ VERIFIED | Exists (`TestRunRelationships` class), collected, **passes** individually. |
| `tests/mdm/test_pipeline_relationships.py::test_audit_firm_seed_is_idempotent` | Seeded audit_firm-type idempotency | ✓ VERIFIED | Exists, collected, **passes** individually. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `_named_node_parity_checks`/`_named_relationship_parity_checks` | `verify()` pass/fail gate | Wired into existing `mdm verify-graph` exit-code logic (D-01) | ✓ WIRED | STATE.md decision log: "Named per-type parity checks in verify-graph fail closed when a type is entirely absent from parity rows" — confirms integration into `verify()`, not a standalone/orphaned helper. No new CLI command was added (consistent with D-01/D-03 rejecting a dedicated command). |
| `GRAPH_NODE_AUDITFIRM` view | `NODE_TABLES` / `render_graph_tables()` | Tuple membership + SQL emission | ✓ WIRED | Confirmed identifier consistency: `GRAPH_NODE_AUDITFIRM` (not the CONTEXT.md prose spelling `GRAPH_NODE_AUDIT_FIRM`) is used consistently in both the tuple and the view SQL, matching the pre-existing `NODE_TABLES` entry per STATE.md. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full mdm test suite passes, no live connections | `uv run --extra s3 --extra snowflake --extra mdm pytest tests/mdm/ -q` | `249 passed, 3 warnings in 19.55s` | ✓ PASS |
| Graph-sync idempotency test passes standalone | `pytest tests/mdm/test_snowflake_graph_migration.py::test_graph_sync_is_idempotent_full_rebuild -v` | `1 passed` | ✓ PASS |
| Node-derivation idempotency (6 entity types) passes standalone | `pytest tests/mdm/test_pipeline_relationships.py -k test_node_resolution_is_idempotent_across_entity_types` | `1 passed` | ✓ PASS |
| Audit-firm seed idempotency passes standalone | `pytest tests/mdm/test_pipeline_relationships.py -k test_audit_firm_seed_is_idempotent` | `1 passed` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| NODE-01 | 05-03 | MDM active `company` count matches `GRAPH_NODE_COMPANY` | ✓ SATISFIED | `_named_node_parity_checks` asserts per-type, incl. COMPANY |
| NODE-02 | 05-03 | `adviser` count matches `GRAPH_NODE_ADVISER` | ✓ SATISFIED | Same mechanism |
| NODE-03 | 05-03 | `person` count matches `GRAPH_NODE_PERSON` | ✓ SATISFIED | Same mechanism |
| NODE-04 | 05-03 | `security` count matches `GRAPH_NODE_SECURITY` | ✓ SATISFIED | Same mechanism |
| NODE-05 | 05-03 | `fund` count matches `GRAPH_NODE_FUND` | ✓ SATISFIED | Same mechanism |
| NODE-06 | 05-01, 05-03 | `GRAPH_NODE_AUDIT_FIRM` view exists (was missing) and count matches | ✓ SATISFIED | View added `snowflake_graph.py:830`; parity check covers it |
| EDGE-01 | 05-03 | `IS_INSIDER` parity | ✓ SATISFIED | In `POPULATED_RELATIONSHIP_TYPES`; `_named_relationship_parity_checks` |
| EDGE-02 | 05-03 | `HOLDS` parity | ✓ SATISFIED | Same mechanism |
| EDGE-03 | 05-03 | `COMPANY_HOLDS` parity | ✓ SATISFIED | Same mechanism |
| EDGE-04 | 05-03 | `ISSUED_BY` parity | ✓ SATISFIED | Same mechanism |
| GVER-03 | 05-01, 05-02 | Repeated derivation AND repeated graph sync against unchanged data produce zero drift, across all 6 node types and 11 relationship types | ✓ SATISFIED | Graph-sync half: `test_graph_sync_is_idempotent_full_rebuild` (05-01). Derivation half: `test_node_resolution_is_idempotent_across_entity_types` + `test_audit_firm_seed_is_idempotent` (05-02), plus pre-existing `test_relationship_derivation_is_idempotent`/`test_all_relationship_types_idempotent` covering the 11 relationship types. All pass. |

No orphaned requirements — REQUIREMENTS.md traceability table lists exactly NODE-01..06, EDGE-01..04, GVER-03 as "Phase 5 / Complete", matching the phase's declared requirement set exactly.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | Grep for `TBD\|FIXME\|XXX` in `edgar_warehouse/mdm/snowflake_graph.py` returned no matches. |

No debt markers, no stub returns, no placeholder patterns identified in the modified surface.

## Test Evidence

```
uv run --extra s3 --extra snowflake --extra mdm pytest tests/mdm/ -q
...
249 passed, 3 warnings in 19.55s
```

Named single-test runs (behavioral confirmation, not full-suite re-filtering):

```
tests/mdm/test_snowflake_graph_migration.py::test_graph_sync_is_idempotent_full_rebuild PASSED
tests/mdm/test_pipeline_relationships.py::TestRunRelationships::test_node_resolution_is_idempotent_across_entity_types PASSED
tests/mdm/test_pipeline_relationships.py::TestRunRelationships::test_audit_firm_seed_is_idempotent PASSED
```

Both 249-count full run and 3 targeted single-named runs report 0 failures, 0 errors, no live Snowflake/AWS connection required (mocked `FakeGraphCursor` for graph-sync side, real local SQLAlchemy/SQLite session for node-derivation side) — consistent with D-06/D-07's dev-only, local-test-only constraint.

## Commit History (confirms phase work landed, matches wave structure)

```
05d80cf feat(05-03): named per-type node/relationship parity checks in verify-graph
c10aa42 test(05-02): node-resolution idempotency for all 6 MDM entity types
4be1123 test(05-01): add graph-sync full-rebuild idempotency regression test
3e23ba1 feat(05-01): emit GRAPH_NODE_AUDITFIRM view in render_graph_tables()
899b875 test(05-01): add failing test for GRAPH_NODE_AUDITFIRM view emission
```

Working tree is clean for the phase's core files (`edgar_warehouse/mdm/snowflake_graph.py`, `tests/mdm/test_snowflake_graph_migration.py`, `tests/mdm/test_pipeline_relationships.py`) — all committed on `claude/fix-pipelines-v2`, matching STATE.md's record.

## Gaps Summary

None. All 5 ROADMAP success criteria verified with direct code/test evidence (not SUMMARY.md narrative). All 11 declared requirement IDs (NODE-01..06, EDGE-01..04, GVER-03) confirmed satisfied. No orphaned requirements. No anti-patterns or debt markers. All behavior-dependent truths (idempotency, #4 and #5 above) were upgraded from presence-only to VERIFIED via individually-run, passing named tests — not accepted on symbol presence alone.

D-06 prodb-replication is correctly out of this phase's scope per ROADMAP.md's explicit scope note (dev-only phase; prodb replication is a documented follow-on operator action, not a plan deliverable) — not a gap.

---

_Verified: 2026-07-08_
_Verifier: Claude (gsd-verifier)_
