# Requirements: fix-pipelines v2.0 — Pipeline Data-Source Completeness & Verification

status: active
milestone: v2.0 fix-pipelines (consolidated)
updated: 2026-07-11

---

## Grafted requirements (consolidation 2026-07-11)

The requirements below are this workstream's native set (NODE/EDGE/ARTF/GVER/EDGX). The
2026-07-11 consolidation also brought in outstanding requirements from two merged workstreams —
these are authoritative in their source files (not re-transcribed here to avoid drift):

- **Phase 10 (Cash Conversion Cycle):** `CCC-01`, `CCC-02` — see the tombstoned
  `.planning/workstreams/fundamental-factors-v2/REQUIREMENTS.md`.
- **Phases 11–15 (Model Builder):** `GOV-01/02/03` and the rest — see
  `.planning/workstreams/fix-pipelines/merged-sources/model-builder-contract-gaps/REQUIREMENTS.md`.

---

## Milestone Requirements

### Node Verification — MDM ↔ Graph

- [x] **NODE-01**: MDM active `company` entity count matches Snowflake `GRAPH_NODE_COMPANY` view count.
- [x] **NODE-02**: MDM active `adviser` entity count matches `GRAPH_NODE_ADVISER` view count.
- [x] **NODE-03**: MDM active `person` entity count matches `GRAPH_NODE_PERSON` view count.
- [x] **NODE-04**: MDM active `security` entity count matches `GRAPH_NODE_SECURITY` view count.
- [x] **NODE-05**: MDM active `fund` entity count matches `GRAPH_NODE_FUND` view count.
- [x] **NODE-06**: A `GRAPH_NODE_AUDIT_FIRM` view exists (currently missing) and its count matches MDM active `audit_firm` entity count (10 seeded Big4/Next6 firms).

### Relationship Verification — MDM ↔ Graph

- [x] **EDGE-01**: `IS_INSIDER` (person→company) — populated; graph parity holds.
- [x] **EDGE-02**: `HOLDS` (person→security) — populated; graph parity holds.
- [x] **EDGE-03**: `COMPANY_HOLDS` (company→security) — populated; graph parity holds.
- [x] **EDGE-04**: `ISSUED_BY` (security→company) — populated; graph parity holds.
- [ ] **EDGE-05**: `IS_ENTITY_OF` (adviser→company) — **no bronze/silver artifact dependency**: pairing comes from MDM's own `mdm_adviser.linked_company_entity_id` resolver field, not from a source document. Currently zero; investigate whether the resolver step that populates this field has ever run, and either populate or document why linkage can't be established (e.g. no adviser CIK in-universe also files as a company).
- [ ] **EDGE-06**: `IS_PERSON_OF` (adviser→person) — **no bronze/silver artifact dependency**: pairing comes from an adviser↔person CIK crosswalk (`MdmAdviser.cik == MdmPerson.owner_cik`), not from a source document. Currently zero; investigate whether any individual-adviser CIKs in-universe also have Form 3/4/5-derived `MdmPerson` records, and either populate or document why no crosswalk matches exist.
- [ ] **EDGE-07**: `MANAGES_FUND` (adviser→fund) — **source artifact: ADV primary attachment documents** (feed `sec_adv_private_fund`). Confirmed unobtainable: all 30 ADV filings in the active universe are EDGAR paper filings with no electronic document (see `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md`). Document as a source-coverage exclusion — no further artifact action is possible from EDGAR.
- [ ] **EDGE-08**: `HAS_PARENT_COMPANY` (company→company) — **no artifact captured or parsed at all** for parent/subsidiary structure (would require 10-K Exhibit 21 or similar, which is not in the current parser surface). This is a missing-parser gap, not a missing-artifact gap — distinct from EDGE-07. Document as a source-coverage exclusion.
- [x] **EDGE-09**: `EMPLOYED_BY` (person→company) — **source artifact: DEF 14A proxy filing documents** (feed `sec_executive_record`). Verify DEF 14A bronze artifacts are actually captured for the active universe. If artifacts are present but `sec_executive_record` is still empty, root-cause the parser/pipeline gap; if artifacts themselves are missing, triage fetchability before concluding a coverage exclusion.
- [x] **EDGE-10**: `AUDITED_BY` (company→audit_firm) — **source artifact: SEC companyfacts (XBRL entity-facts) API responses** (feed `sec_accounting_flag.auditor_pcaob_id`). Artifact is confirmed fetchable (not a paper-filing-style dead end) — populate once a fundamentals entity-facts run publishes to the unified `silver/sec/silver.duckdb` (coordinate with the `fundamental-factors-v2` workstream — do not run fundamentals in dev without checking for overlap).
- [x] **EDGE-11**: `INSTITUTIONAL_HOLDS` (adviser→security) — **source artifact: 13F-HR INFORMATION TABLE XML documents** (feed `sec_thirteenf_holding`). Verify 13F bronze artifacts are actually captured for institutional advisers in the active universe. If artifacts are present but the table is still empty, root-cause the parser/pipeline gap; if artifacts themselves are missing, triage fetchability before concluding a coverage exclusion.

### Cross-Cutting Graph Verification

- [x] **GVER-01**: `mdm verify-graph` output distinguishes Native App readiness failures (e.g. no compute pool available) from actual MDM↔graph parity failures.
- [x] **GVER-02**: Any Neo4j Graph Analytics Native App capability still broken app-side (GRAPH_INFO, BFS, LIST_GRAPHS per PR #122 findings) is fixed or documented with exact reproducing commands/dates, distinct from MDM-side issues. Stable documented operations define required capability health; experimental `LIST_GRAPHS` remains an informational external diagnostic.
- [x] **GVER-03**: Repeated MDM relationship derivation AND repeated graph sync against unchanged data produce zero drift (idempotent) across all 6 node types and 11 relationship types. (Graph-sync/full-rebuild side proven by 05-01's `test_graph_sync_is_idempotent_full_rebuild`; node/relationship-derivation side proven by 05-02's `test_node_resolution_is_idempotent_across_entity_types` and `test_audit_firm_seed_is_idempotent` — both halves complete.)

### Missing Source Artifacts

Per-relationship artifact triage (which source documents feed which relationship, and whether
they're fetchable) is captured directly in EDGE-05 through EDGE-11 above rather than as a
separate generic audit — each relationship's artifact dependency (or explicit absence of one)
is stated where it's actionable. This section covers only the two cross-cutting artifact-integrity
mechanisms that aren't tied to any single relationship type.

- [ ] **ARTF-01**: Silver-publishing warehouse commands (`parse-adv-bronze` and peers) never overwrite a healthier canonical `silver.duckdb` with a smaller/incomplete local copy — publish is skipped or guarded when the local copy would regress the canonical.
- [ ] **ARTF-02**: Any newly-captured artifact fetch (from EDGE-09/EDGE-11 triage or elsewhere) honors SEC idempotency (DEC-009) — already-captured filings are not re-fetched without an explicit `--force`.

### Verified MDM → Neo4j Relationship Generations

- [x] **RPRE-01**: Before Phase 7 schema implementation, a live dev preflight using `SNOW_CONNECTION=snowconn` proves the Snowflake-hosted Neo4j Native App can load the contract views, expose typed date edge properties, execute supported graph metadata and BFS/multi-hop operations, and observe a stable-view test-generation switch. Required health uses documented stable operations plus semantic MDM↔graph parity; graph discovery uses the platform-owned generation registry. Experimental `LIST_GRAPHS` is informational and cannot independently block implementation. Verified GO on 2026-07-12 and human-approved.
- [ ] **RSYNC-01**: PostgreSQL MDM is the relationship derivation/staging authority, while both MDM serving reads and Snowflake-hosted Neo4j reads expose the same verified active generation.
- [ ] **RSYNC-02**: Each generation contains a complete node-and-edge snapshot and activates through one guarded Snowflake pointer only after identity-, property-, temporal-, endpoint-, and coverage-level verification passes for every registered type.
- [ ] **RSYNC-03**: MDM commits graph-publication requests transactionally; a centralized publisher targets activation within five minutes, alerts after fifteen minutes, and never requires individual ingestion commands to implement graph synchronization.
- [ ] **RSYNC-04**: Generation assembly fans out immutable type-first partitions in parallel, selectively hash-shards high-volume types, reuses content-addressed unchanged partitions, and independently retries failed partitions before fan-in.
- [ ] **RSYNC-05**: Failed/incomplete generations never become visible; the prior verified generation remains active, and rollback can select a retained verified generation. Retention keeps at least three generations and all generations from the prior 30 days.
- [ ] **RTEMP-01**: Relationships have stable logical and version identifiers plus date-only `[valid_from_date, valid_to_date)` validity, explicit date provenance, and synchronized typed temporal properties in MDM and Neo4j.
- [ ] **RTEMP-02**: Active graph generations retain complete non-quarantined relationship history; strict `as_of_date` traversal excludes temporally unproven edges unless uncertainty is explicitly requested and labeled.
- [ ] **RTEMP-03**: Direct relationships remain authoritative in MDM; multi-hop paths are queried in Neo4j, while materialized derived edges require deterministic rules, provenance, freshness policy, and an explicit derived label.
- [ ] **RTEMP-04**: Conflicting temporal overlaps follow relationship-specific source-priority/tie-break policies; unresolved conflicts are quarantined and block activation. Ordinary workflows never physically delete relationship history.
- [ ] **RCOV-01**: Every registered relationship type has exactly one per-generation coverage status: `populated`, freshly-proven `valid_zero`, or current-evidence `excluded`; any missing, stale, contradictory, or undocumented status blocks activation.
- [ ] **RCOV-02**: EDGE-07 is machine-readably classified `source_unavailable` and EDGE-08 `capability_not_implemented`, each with relationship-specific evidence fingerprints and no synthetic graph edges.
- [ ] **RLINE-01**: Entity merges remap graph traversal to the surviving canonical entity while preserving original source identity and merge lineage; edge IDs and relationship-version IDs remain stable across generations.

### edgartools Crosscheck

- [ ] **EDGX-01**: A documented sample-filing comparison shows whether platform-parsed ownership/ADV/financials output agrees with `edgartools`-produced output for the same filings, with discrepancies explained.
- [ ] **EDGX-02**: Each hand-built parser in the platform (ownership, ADV, financials) is evaluated against current `edgartools` coverage; parsers with equivalent, well-supported edgartools coverage are replaced or have a documented reason not to be.
- [ ] **EDGX-03**: Platform's edgartools API usage (imports, call patterns) is audited against the pinned version's current, non-deprecated surfaces per the edgartools changelog.

## Future Requirements

- [ ] IARD/IAPD ingestion pipeline (non-EDGAR data source) to recover structured ADV adviser/private-fund data that paper filings cannot provide — new pipeline, out of this milestone's scope.
- [ ] Automated recurring edgartools-vs-platform drift detection (rather than a one-time documented sample comparison).

## Out Of Scope

- Building a new non-EDGAR ADV data source (IARD/IAPD) — the paper-filing gap is documented, not solved, this milestone.
- Running fundamentals entity-facts loads that conflict with the active `fundamental-factors-v2` workstream without explicit coordination.
- Real prod (AWS account `077127448006`, Snowflake `EDGARTOOLS_PROD`) — dev (`690839588395`) and `EDGARTOOLS_PRODB` only.
- Non-AWS deployment paths, registries, storage targets, or secret-management paths (DEC-001).
- Gold table/dbt model redesign unrelated to proving the relationship/graph verification path.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NODE-01 | Phase 5 | Complete |
| NODE-02 | Phase 5 | Complete |
| NODE-03 | Phase 5 | Complete |
| NODE-04 | Phase 5 | Complete |
| NODE-05 | Phase 5 | Complete |
| NODE-06 | Phase 5 | Complete |
| EDGE-01 | Phase 5 | Complete |
| EDGE-02 | Phase 5 | Complete |
| EDGE-03 | Phase 5 | Complete |
| EDGE-04 | Phase 5 | Complete |
| GVER-03 | Phase 5 | Complete |
| EDGE-05 | Phase 6 | Pending |
| EDGE-06 | Phase 6 | Pending |
| EDGE-09 | Phase 6 | Complete |
| EDGE-10 | Phase 6 | Complete |
| EDGE-11 | Phase 6 | Complete |
| EDGE-07 | Phase 7 | Pending |
| EDGE-08 | Phase 7 | Pending |
| ARTF-01 | Phase 7 | Pending |
| ARTF-02 | Phase 7 | Pending |
| RPRE-01 | Phase 7 | Complete |
| RSYNC-01 | Phase 7 | Pending |
| RSYNC-02 | Phase 7 | Pending |
| RSYNC-03 | Phase 7 | Pending |
| RSYNC-04 | Phase 7 | Pending |
| RSYNC-05 | Phase 7 | Pending |
| RTEMP-01 | Phase 7 | Pending |
| RTEMP-02 | Phase 7 | Pending |
| RTEMP-03 | Phase 7 | Pending |
| RTEMP-04 | Phase 7 | Pending |
| RCOV-01 | Phase 7 | Pending |
| RCOV-02 | Phase 7 | Pending |
| RLINE-01 | Phase 7 | Pending |
| GVER-01 | Phase 8 | Complete |
| GVER-02 | Phase 8 | Complete |
| EDGX-01 | Phase 9 | Pending |
| EDGX-02 | Phase 9 | Pending |
| EDGX-03 | Phase 9 | Pending |
