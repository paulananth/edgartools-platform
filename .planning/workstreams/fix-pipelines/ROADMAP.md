# Roadmap: fix-pipelines v2.0 — Pipeline Data-Source Completeness & Verification

status: active
milestone: v2.0 fix-pipelines
updated: 2026-07-08

---

## Milestone Goal

Close the remaining data-source and verification gaps across the MDM → Neo4j graph pipeline so
every node type and every relationship type is either verified-populated or has a written,
evidenced source-coverage exclusion — with each exclusion traced to its actual source artifact
(or explicit absence of one) rather than treated as generic pipeline hygiene — and platform
parsing is cross-checked against, and where it's a clear win replaced by, the `edgartools`
reference library.

---

## Phases

- [ ] **Phase 5: Node And Populated-Relationship Graph Parity** - every MDM node type syncs to a verifiable per-type graph view, the 4 already-populated relationship types have proven MDM↔graph parity, and derivation/sync idempotency is established as a repeatable check.
- [ ] **Phase 6: Relationship Investigation And Population** - root-cause each still-ambiguous zero relationship type against its actual source artifact (or confirm it has none), and populate whichever ones the investigation shows are unblocked.
- [ ] **Phase 7: Source-Coverage Exclusions And Artifact Hygiene** - formally document the two artifact-confirmed-unsatisfiable relationship types, and close the two cross-cutting artifact-integrity gaps found during this milestone's investigation.
- [ ] **Phase 8: Neo4j Native App Verification Gaps** - `mdm verify-graph` cleanly separates environment/readiness problems from real parity problems, and app-side capability gaps are resolved or conclusively documented.
- [ ] **Phase 9: edgartools Crosscheck** - platform parsing is validated against edgartools, hand-built parsers are replaced where edgartools already covers the same ground well, and API usage is confirmed current.

---

## Phase Details

### Phase 5: Node And Populated-Relationship Graph Parity
**Goal**: Every MDM node type syncs to a verifiable per-type graph view, the 4 already-populated relationship types have proven MDM↔graph parity, and derivation/sync idempotency is established as a repeatable check.
**Depends on**: Nothing new — builds on the existing sync-graph/verify-graph code (PR #122 Native App API rework).
**Requirements**: NODE-01, NODE-02, NODE-03, NODE-04, NODE-05, NODE-06, EDGE-01, EDGE-02, EDGE-03, EDGE-04, GVER-03
**Success Criteria** (what must be TRUE):
  1. All 6 MDM entity types (company, adviser, person, security, fund, audit_firm) have a corresponding `GRAPH_NODE_*` view in Snowflake, including a newly-added `GRAPH_NODE_AUDIT_FIRM` (confirmed missing this session).
  2. Node-type counts (MDM active vs graph view) match exactly for all 6 types in dev.
  3. The 4 populated relationship types (IS_INSIDER, HOLDS, COMPANY_HOLDS, ISSUED_BY) show exact MDM-to-graph parity via their `GRAPH_EDGE_*` views.
  4. Running MDM relationship derivation twice against unchanged silver data produces zero new/duplicate active rows for the 4 populated types.
  5. Running `mdm sync-graph` twice against unchanged MDM data produces stable node and edge counts.
**Plans**: 3 plans
- [ ] 05-01-PLAN.md — Emit GRAPH_NODE_AUDITFIRM view + graph-sync full-rebuild idempotency test (NODE-06, GVER-03)
- [ ] 05-02-PLAN.md — Real-DB node-derivation idempotency test for all 6 entity types (GVER-03)
- [ ] 05-03-PLAN.md — Named per-type verify-graph parity checks for 6 node + 4 populated edge types (NODE-01..06, EDGE-01..04)

**D-06 scope note (plan-checker WARNING resolved 2026-07-08):** 05-01/02/03 are dev-only —
success criteria 1-5 above are all dev-side (`EDGARTOOLS_DEV`). CONTEXT.md D-06 ("once dev is
green, replicate to `EDGARTOOLS_PRODB`") is intentionally NOT a 4th PLAN.md: it's an operator
deploy+verify action (run the existing `deploy-aws-application.sh`/`deploy-snowflake-stack.sh`
tooling, then re-run `mdm verify-graph` pointed at `EDGARTOOLS_PRODB`), not a code-authoring
task with TDD acceptance criteria. Sequencing was reserved as Claude's Discretion in
`05-CONTEXT.md`. Phase 5 is dev-complete once 05-01/02/03 execute and verify green; the prodb
replication step is a follow-on operator action after that, tracked here rather than silently
dropped.

### Phase 6: Relationship Investigation And Population
**Goal**: Root-cause each still-ambiguous zero relationship type against its actual source artifact (or confirm it has none), and populate whichever ones the investigation shows are unblocked.
**Depends on**: Phase 5 (verification harness must exist to prove any newly-populated rows sync correctly).
**Requirements**: EDGE-05, EDGE-06, EDGE-09, EDGE-10, EDGE-11
**Success Criteria** (what must be TRUE):
  1. IS_ENTITY_OF's zero-row status is root-caused against `mdm_adviser.linked_company_entity_id` (no source artifact involved — either the resolver step runs and populates it, or the gap is confirmed structural and documented).
  2. IS_PERSON_OF's zero-row status is root-caused against the adviser↔person CIK crosswalk (no source artifact involved — either matches exist and populate, or the gap is confirmed structural and documented).
  3. EMPLOYED_BY's zero-row status is root-caused against DEF 14A proxy artifact coverage: confirm whether DEF 14A bronze artifacts exist for the active universe, and if so why `sec_executive_record` is still empty; if not, triage fetchability.
  4. INSTITUTIONAL_HOLDS's zero-row status is root-caused against 13F-HR artifact coverage: confirm whether 13F bronze artifacts exist for institutional advisers in the active universe, and if so why `sec_thirteenf_holding` is still empty; if not, triage fetchability.
  5. AUDITED_BY derives nonzero rows in dev once the fundamentals entity-facts prerequisite (SEC companyfacts artifact, confirmed fetchable) lands, coordinated with the `fundamental-factors-v2` workstream to avoid overlap.
  6. Every relationship type investigated in this phase ends with either nonzero graph-verified rows or a written, evidenced source-coverage exclusion that names its artifact dependency (or explicit absence of one) — no type exits this phase in an undocumented zero state.
**Plans**: TBD

### Phase 7: Source-Coverage Exclusions And Artifact Hygiene
**Goal**: Formally document the two artifact-confirmed-unsatisfiable relationship types, and close the two cross-cutting artifact-integrity gaps found during this milestone's investigation.
**Depends on**: Nothing new — MANAGES_FUND/HAS_PARENT_COMPANY root causes are already confirmed; the two ARTF items are infra-level and independent of Phase 6's outcomes.
**Requirements**: EDGE-07, EDGE-08, ARTF-01, ARTF-02
**Success Criteria** (what must be TRUE):
  1. MANAGES_FUND has a written source-coverage exclusion naming its exact blocked artifact (ADV primary attachment documents — confirmed paper filings, `claude-mdm-source-recovery/FINDINGS.md`), cross-referenced from REQUIREMENTS.md and PROJECT.md.
  2. HAS_PARENT_COMPANY has a written source-coverage exclusion distinguishing it from EDGE-07: no artifact is missing, no parser exists at all for parent/subsidiary structure (e.g. 10-K Exhibit 21).
  3. Silver-publishing commands (`parse-adv-bronze` and peers) skip republishing the canonical `silver.duckdb` when the local copy would be smaller/incomplete relative to the current canonical, verified by a regression test.
  4. Any artifact newly fetched during Phase 6's EDGE-09/EDGE-11 triage is verified to skip already-captured filings by default (idempotency, DEC-009).
**Plans**: TBD

### Phase 8: Neo4j Native App Verification Gaps
**Goal**: `mdm verify-graph` cleanly separates environment/readiness problems from real parity problems, and the app-side capability gaps identified in PR #122 (GRAPH_INFO/BFS/LIST_GRAPHS) are resolved or conclusively documented as external blockers.
**Depends on**: Phase 5 (extends the same verify-graph baseline).
**Requirements**: GVER-01, GVER-02
**Success Criteria** (what must be TRUE):
  1. A verify-graph run against a Snowflake account with no available compute pool produces a distinct, clearly-labeled readiness failure rather than being reported as a parity failure.
  2. GRAPH_INFO, BFS, and LIST_GRAPHS are each individually re-tested against the current Native App release; each either passes, or has a dated reproduction command and error captured as an external blocker.
  3. verify-graph's overall exit code and summary output make it unambiguous to an operator whether a failure is "fix your Snowflake environment" or "fix your MDM/graph data."
**Plans**: TBD

### Phase 9: edgartools Crosscheck
**Goal**: Platform parsing is validated against the edgartools reference library, with hand-built parsers replaced where edgartools already covers the same ground well, and API usage confirmed current.
**Depends on**: Nothing new — independent of Phases 5-8; benefits from a stable pipeline but doesn't require one.
**Requirements**: EDGX-01, EDGX-02, EDGX-03
**Success Criteria** (what must be TRUE):
  1. A documented comparison exists for a defined sample of filings (ownership, ADV, financials) showing platform-parsed vs edgartools-parsed field-level agreement, with any discrepancies explained.
  2. Each of the platform's hand-built parsers (ownership, ADV, financials) has a documented replace-or-keep decision against current edgartools coverage, with at least one migrated to edgartools-native parsing if a clear win exists.
  3. The platform's edgartools import/API surface (`Ownership.from_xml`, `edgar.filing`, `edgar.entity`, `edgar.xbrl`) is confirmed non-deprecated against the pinned version's changelog, with any findings documented.
**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 5. Node And Populated-Relationship Graph Parity | v2.0 fix-pipelines | 0/TBD | Not started | - |
| 6. Relationship Investigation And Population | v2.0 fix-pipelines | 0/TBD | Not started | - |
| 7. Source-Coverage Exclusions And Artifact Hygiene | v2.0 fix-pipelines | 0/TBD | Not started | - |
| 8. Neo4j Native App Verification Gaps | v2.0 fix-pipelines | 0/TBD | Not started | - |
| 9. edgartools Crosscheck | v2.0 fix-pipelines | 0/TBD | Not started | - |
