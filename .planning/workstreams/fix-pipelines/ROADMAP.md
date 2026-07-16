# Roadmap: fix-pipelines v2.0 — Pipeline Data-Source Completeness & Verification (CONSOLIDATED)

status: active
milestone: v2.0 fix-pipelines (consolidated active workstream)
updated: 2026-07-11

---

## ⚠️ Consolidation note (2026-07-11)

On 2026-07-11 this workstream became the **single active workstream** ("combine all active
workstreams", in-progress-only). It is the spine; the outstanding phases of two other
workstreams were grafted onto the end of its roadmap:

| Unified phase | Origin | Notes |
|---------------|--------|-------|
| 06–09 | fix-pipelines (native) | Phases 5–9 are this workstream's own; 5 done, 6 paused, 7–9 unbuilt |
| **10** Cash Conversion Cycle | `fundamental-factors-v2` Phase 3 | grafted (Codex→Claude hand-off); files renumbered `03-*`→`10-*`; see `phases/10-cash-conversion-cycle/10-MERGE-NOTE.md` |
| **11–15** Model Builder contract | `model-builder-contract-gaps` Phases 1–6 | not yet built; charter in `merged-sources/model-builder-contract-gaps/`; 14–15 remain charter-held |

Source workstreams `fundamental-factors-v2` and `model-builder-contract-gaps` are **tombstoned**
(their `STATE.md` marked `merged-into-fix-pipelines`) — do not resume them separately. Their
completed phases stay in place as history. Excluded from the merge (already complete): `go-live`,
`mdm-neo4j-dashboard`, `neo4j-snowflake`, `neo4j-pipe`. Rollback snapshot: scratchpad
`planning-pre-merge-*.tgz`.

---

## Milestone Goal

Close the remaining data-source and verification gaps across the MDM → Neo4j graph pipeline so
every node type and every relationship type is either verified-populated or has a written,
evidenced source-coverage exclusion — with each exclusion traced to its actual source artifact
(or explicit absence of one) rather than treated as generic pipeline hygiene — and platform
parsing is cross-checked against, and where it's a clear win replaced by, the `edgartools`
reference library.

**Consolidated scope (added 2026-07-11):** additionally deliver the Cash Conversion Cycle gold
factors (Phase 10, ex-`fundamental-factors-v2`) and the Model Builder source-contract expansion
(Phases 11–15, ex-`model-builder-contract-gaps`).

---

## Phases

- [x] **Phase 5: Node And Populated-Relationship Graph Parity** - every MDM node type syncs to a verifiable per-type graph view, the 4 already-populated relationship types have proven MDM↔graph parity, and derivation/sync idempotency is established as a repeatable check. (completed 2026-07-08)
- [ ] **Phase 6: Relationship Investigation And Population** - root-cause each still-ambiguous zero relationship type against its actual source artifact (or confirm it has none), and populate whichever ones the investigation shows are unblocked.
- [ ] **Phase 7: Source-Coverage Exclusions And Artifact Hygiene** - formally document the two artifact-confirmed-unsatisfiable relationship types, and close the two cross-cutting artifact-integrity gaps found during this milestone's investigation.
- [x] **Phase 8: Neo4j Native App Verification Gaps** - `mdm verify-graph` cleanly separates environment/readiness problems from real parity problems, and app-side capability gaps are resolved or conclusively documented.
- [ ] **Phase 9: edgartools Crosscheck** - platform parsing is validated against edgartools, hand-built parsers are replaced where edgartools already covers the same ground well, and API usage is confirmed current.

### Consolidated phases (grafted 2026-07-11)

- [ ] **Phase 10: Cash Conversion Cycle** *(ex fundamental-factors-v2 Phase 3)* - expose DSO/DIO/DPO gold factors from already-fetched companyfacts, or formally declare out of scope if `cost_of_revenue` XBRL coverage is too poor. Plans built (`10-01`, `10-02`), not executed.
- [ ] **Phase 11: Model Builder — Contract Governance & Compatibility Boundary** *(ex model-builder Phase 1)* - lock the source-of-truth boundary and classify each Model Builder gap as in-scope / out-of-scope / charter-blocked. **Must complete before Phases 12–15.** Not yet planned.
- [ ] **Phase 12: Model Builder — Statement Metadata + Data-Quality Signals** *(ex model-builder Phases 2+3, paired)* - enrich gold with statement display metadata/lineage and expose source data-quality signals. Not yet planned.
- [ ] **Phase 13: Model Builder — Citation Source Reference Contract** *(ex model-builder Phase 4)* - expose citation-ready source references and fact-to-source lineage. Not yet planned.
- [ ] **Phase 14: Model Builder — Market Data Contract** *(ex model-builder Phase 5)* - **HELD (charter decision required)** before activation.
- [ ] **Phase 15: Model Builder — Peer & Estimate Contract** *(ex model-builder Phase 6)* - **HELD (charter decision required)** before activation.

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

**Plans**: 3/3 plans complete
**Wave 1**

- [x] 05-01-PLAN.md — Emit GRAPH_NODE_AUDITFIRM view + graph-sync full-rebuild idempotency test (NODE-06, GVER-03)
- [x] 05-02-PLAN.md — Real-DB node-derivation idempotency test for all 6 entity types (GVER-03)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-03-PLAN.md — Named per-type verify-graph parity checks for 6 node + 4 populated edge types (NODE-01..06, EDGE-01..04)

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

**Plans**: 2/6 plans executed

**Wave 1** *(parallel — no load dependency)*

- [x] 06-01-PLAN.md — INSTITUTIONAL_HOLDS CIK-range batched read (D-03, EDGE-11 code)
- [x] 06-02-PLAN.md — Root-cause the 2026-07-06 bootstrap Step Function failure + load_history readiness verdict (D-01)

**Wave 2** *(the operational load — depends on Wave 1)*

- [ ] 06-03-PLAN.md — Bounded ~100-200 company load_history dev run + per-type artifact-coverage evidence (D-02)

**Wave 3** *(per-type investigation + population/exclusion — depends on 06-03)*

- [ ] 06-04-PLAN.md — EDGE-09 (EMPLOYED_BY) + EDGE-11 (INSTITUTIONAL_HOLDS) populate-or-exclude
- [ ] 06-05-PLAN.md — EDGE-10 (AUDITED_BY) populate-or-exclude + fundamental-factors-v2 coordination

**Wave 4** *(closure — depends on 06-04, 06-05)*

- [ ] 06-06-PLAN.md — EDGE-05/06 SQL-confirmed closure (D-04) + POPULATED_RELATIONSHIP_TYPES extension (D-05) + phase closure ledger

### Phase 7: Relationship Graph Consistency, Temporal Lineage, And Artifact Hygiene

**Goal**: Make MDM relationship truth and the Snowflake-hosted Neo4j query projection consumer-visible as one verified, temporal, rollback-safe generation, with exhaustive source-coverage evidence and semantic guards on every relationship input.
**Depends on**: Phase 6 for the final relationship population/zero-state ledger; Phase 5 for graph identity/parity foundations.
**Requirements**: EDGE-07, EDGE-08, ARTF-01, ARTF-02, RPRE-01, RSYNC-01, RSYNC-02, RSYNC-03, RSYNC-04, RSYNC-05, RTEMP-01, RTEMP-02, RTEMP-03, RTEMP-04, RCOV-01, RCOV-02, RLINE-01
**Success Criteria** (what must be TRUE):

  1. A live dev Native App preflight proves contract-view loading, typed date edge properties, supported graph metadata and BFS/multi-hop operations, and stable-view generation switching before schema implementation begins. Semantic MDM↔graph parity defines health; the platform-owned generation registry defines discovery; experimental Native App inventory endpoints are informational only.
  2. Every registered relationship type is `populated`, freshly-proven `valid_zero`, or current-evidence `excluded`; stale or undocumented coverage blocks generation activation.
  2. MANAGES_FUND is `source_unavailable` and HAS_PARENT_COMPANY is `capability_not_implemented`, each with exact evidence fingerprints and no synthetic graph edges.
  3. Relationships retain stable logical/version IDs, date-only half-open validity, date provenance, source lineage, non-destructive history, and typed temporal properties in both MDM and graph edges.
  4. PostgreSQL MDM commits publication requests transactionally; immutable node/relationship partitions build in parallel, retry/reuse independently, and fan in to a complete generation.
  5. Both MDM serving and Neo4j views select through one Snowflake active-generation pointer; identity, property, endpoint, temporal, and coverage verification all pass before atomic activation.
  6. Current and historical multi-hop queries return only edges provably valid for the requested date by default; uncertain dates require explicit opt-in and labeling.
  7. Entity merges restore canonical graph connectivity while preserving original source identities and merge lineage.
  8. Failed builds leave the prior generation active; verified generations can roll back within the locked three-generation/30-day retention floor.
  9. Silver publication merges partial candidates semantically without losing protected keys, rejects ambiguous row conflicts, and aborts optimistic promotion when canonical S3 state changes.
  10. Intact bronze artifacts cause zero SEC network calls; explicit bronze repair remains audited and cannot bypass silver monotonicity.
  12. Normal publication meets the five-minute target and emits a hard operational alert after fifteen minutes; bounded backfills declare their publication window.

**Plans**: 6/8 plans executed; 07-07 Task 1 (repeatable rehearsal script + test) executed, Tasks 2-3 blocked on a required human-verify checkpoint (see 07-07-PLAN.md; not autonomous)

- [x] 07-00-PLAN.md — Live Snowflake-hosted Neo4j Native App capability preflight and dated GO evidence
- [x] 07-01-PLAN.md — Stable relationship/version identity, date-only temporal contract, provenance, direct/derived rules, source priority, and non-destructive conflict handling
- [x] 07-02-PLAN.md — Exhaustive generation coverage manifest, per-generation valid-zero evidence, and EDGE-07/08 machine-readable exclusions
- [x] 07-03-PLAN.md — Transactional MDM publication queue, watermarks, lifecycle states, five/fifteen-minute freshness health, and alerts
- [x] 07-04-PLAN.md — Parallel type-first generation partitions, selective hash sharding, content-addressed reuse, independent retry, and fan-in manifests (partial: per-partition Snowflake row write and pipeline chaining deferred; see RSYNC-04)
- [x] 07-05-PLAN.md — Snowflake active-generation serving boundary, complete node/edge parity, temporal graph queries, canonical entity remap, atomic activation, rollback, and retention
- [x] 07-06-PLAN.md — Semantic silver merge/promotion, protected-table/conflict policies, optimistic S3 concurrency, global bronze idempotency, and audited repair
- [ ] 07-07-PLAN.md — Bounded dev rehearsal proving exclusions, temporal/multi-hop behavior, concurrency, retry/reuse, activation safety, and rollback (Task 1 done; Task 2 requires a human operator to run the rehearsal against AWS/Snowflake dev and type `approved`; Task 3's `07-VERIFICATION.md` cannot be marked `passed` until then)

### Phase 8: Neo4j Native App Verification Gaps

**Goal**: `mdm verify-graph` cleanly separates environment/readiness problems from real parity problems, and the app-side capability gaps identified in PR #122 (GRAPH_INFO/BFS/LIST_GRAPHS) are resolved or conclusively documented as external blockers.
**Depends on**: Phase 5 (extends the same verify-graph baseline).
**Requirements**: GVER-01, GVER-02
**Success Criteria** (what must be TRUE):

  1. A verify-graph run against a Snowflake account with no available compute pool produces a distinct, clearly-labeled readiness failure rather than being reported as a parity failure.
  2. GRAPH_INFO, BFS, and LIST_GRAPHS are each individually re-tested against the current Native App release; each either passes, or has a dated reproduction command and error captured as an external blocker.
  3. verify-graph's overall exit code and summary output make it unambiguous to an operator whether a failure is "fix your Snowflake environment" or "fix your MDM/graph data."

**Plans**: 2/2 plans complete

- [x] 08-01-PLAN.md — Current GRAPH_INFO/BFS/LIST_GRAPHS API compatibility and readiness/parity/capability classification
- [x] 08-02-PLAN.md — Live dev capability evidence and external-blocker verification

### Phase 9: edgartools Crosscheck

**Goal**: Platform parsing is validated against the edgartools reference library, with hand-built parsers replaced where edgartools already covers the same ground well, and API usage confirmed current.
**Depends on**: Nothing new — independent of Phases 5-8; benefits from a stable pipeline but doesn't require one.
**Requirements**: EDGX-01, EDGX-02, EDGX-03
**Success Criteria** (what must be TRUE):

  1. A documented comparison exists for a defined sample of filings (ownership, ADV, financials) showing platform-parsed vs edgartools-parsed field-level agreement, with any discrepancies explained.
  2. Each of the platform's hand-built parsers (ownership, ADV, financials) has a documented replace-or-keep decision against current edgartools coverage, with at least one migrated to edgartools-native parsing if a clear win exists.
  3. The platform's edgartools import/API surface (`Ownership.from_xml`, `edgar.filing`, `edgar.entity`, `edgar.xbrl`) is confirmed non-deprecated against the pinned version's changelog, with any findings documented.

**Plans**: TBD

### Phase 10: Cash Conversion Cycle  *(grafted — ex `fundamental-factors-v2` Phase 3)*

**Goal**: Consumers can query Days Sales Outstanding, Days Inventory Outstanding, and Days Payable Outstanding — or CCC is explicitly declared out of scope if `cost_of_revenue` XBRL-tag coverage is too poor to be useful.
**Depends on**: Nothing in this workstream (research-gated; coverage resolved acceptable per its D-01).
**Requirements**: CCC-01, CCC-02 (see `merged-sources`/original `fundamental-factors-v2/REQUIREMENTS.md`).
**Plans**: 2/2 built, 0 executed — `phases/10-cash-conversion-cycle/10-01-PLAN.md` (DSO macro + tests), `10-02-PLAN.md` (cost_of_revenue/accounts_payable silver fields + DIO/DPO). Full detail (goal, success criteria, waves) in that dir; **internal prose still says "Phase 3"** — see `10-MERGE-NOTE.md`.

### Phases 11–15: Model Builder Source Contract Expansion  *(grafted — ex `model-builder-contract-gaps`)*

**Not yet planned** (source workstream was at charter/planning stage, zero phases built). Full
charter, requirements, and phase definitions: `merged-sources/model-builder-contract-gaps/`
(`ROADMAP.md`, `REQUIREMENTS.md`, `INTAKE.md`, `PROJECT.md`).

- **Phase 11 — Contract Governance & Compatibility Boundary** *(model-builder P1)*: lock source-of-truth boundary; classify each gap in/out/charter-blocked. Requirements GOV-01/02/03. **Gates 12–15.**
- **Phase 12 — Statement Metadata + Data-Quality Signals** *(model-builder P2+P3, paired)*: gold statement display metadata/lineage + source data-quality signals.
- **Phase 13 — Citation Source Reference Contract** *(model-builder P4)*: citation-ready source references + fact-to-source lineage.
- **Phase 14 — Market Data Contract** *(model-builder P5)*: **HELD** — activates only after a platform charter decision (own vs external-provider vs out-of-scope).
- **Phase 15 — Peer & Estimate Contract** *(model-builder P6)*: **HELD** — same charter deferral (SIC-based peer clusters already exist via `COMPANY.sic_code`; only advanced peer-suggestion contracts are held).

---

## Progress

| Phase | Origin | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 5. Node And Populated-Relationship Graph Parity | fix-pipelines | 3/3 | Complete    | 2026-07-08 |
| 6. Relationship Investigation And Population | fix-pipelines | 3/6 | In Progress (06-03 done; next 06-04) |  |
| 7. Source-Coverage Exclusions And Artifact Hygiene | fix-pipelines | 0/TBD | Not started | - |
| 8. Neo4j Native App Verification Gaps | fix-pipelines | 0/TBD | Not started | - |
| 9. edgartools Crosscheck | fix-pipelines | 0/TBD | Not started | - |
| 10. Cash Conversion Cycle | ex fundamental-factors-v2 | 0/2 | Not started (planned) | - |
| 11. Model Builder — Contract Governance | ex model-builder | 0/TBD | Not started (unplanned) | - |
| 12. Model Builder — Statement Metadata + Quality | ex model-builder | 0/TBD | Not started (unplanned) | - |
| 13. Model Builder — Citation Contract | ex model-builder | 0/TBD | Not started (unplanned) | - |
| 14. Model Builder — Market Data | ex model-builder | 0/TBD | HELD (charter) | - |
| 15. Model Builder — Peer & Estimate | ex model-builder | 0/TBD | HELD (charter) | - |
