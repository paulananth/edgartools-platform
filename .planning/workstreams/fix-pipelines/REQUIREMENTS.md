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
- [x] **EDGE-05**: `IS_ENTITY_OF` (adviser→company) — **no bronze/silver artifact dependency**: pairing comes from MDM's own `mdm_adviser.linked_company_entity_id` resolver field, not from a source document. **Disposed 2026-07-13 (Phase 6, 06-06): EXCLUDED — source-coverage exclusion scoped to the current tracking-list universe.** D-04 SQL-confirmed zero-overlap: 0 of 1 adviser's CIK matches any company CIK. See `06-PHASE-CLOSURE-LEDGER.md`. Re-check required if the adviser universe grows.
- [x] **EDGE-06**: `IS_PERSON_OF` (adviser→person) — **no bronze/silver artifact dependency**: pairing comes from an adviser↔person CIK crosswalk (`MdmAdviser.cik == MdmPerson.owner_cik`), not from a source document. **Disposed 2026-07-13 (Phase 6, 06-06): EXCLUDED — source-coverage exclusion scoped to the current tracking-list universe.** D-04 SQL-confirmed zero-overlap: 0 of 1 adviser's CIK matches any of 45 persons' `owner_cik`. See `06-PHASE-CLOSURE-LEDGER.md`. Re-check required if the adviser universe grows.
- [x] **EDGE-07**: `MANAGES_FUND` (adviser→fund) — **source artifact: ADV primary attachment documents** (feed `sec_adv_private_fund`). **Disposed 2026-07-13/14 (Phase 7, 07-02): EXCLUDED — `source_unavailable`.** The `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md` reference cited previously does not exist (only an open-investigation `CLAUDE-INSTRUCTIONS.md` remains in that directory) — re-verified live instead: `sec_company_filing`'s 30 ADV-family filings in the tracked universe are all `ADV-E`/`ADV-NR` (11 CIKs), never a primary `ADV`/`ADV-A` entry; confirmed against live SEC EDGAR `submissions.json` for 3 of those CIKs (each shows only `ADV-E`/`13F-HR`/`N-PX` in its full filing history). Form ADV Part 1A/Schedule D (the private-fund document) is filed through IARD, not EDGAR — a structural, non-EDGAR-artifact gap, not a paper-filing technicality. Machine-readable, fingerprinted in `edgar_warehouse/mdm/coverage.py:compute_edge07_manages_fund_coverage`. See `07-01-SUMMARY.md`/`07-02-SUMMARY.md`.
- [x] **EDGE-08**: `HAS_PARENT_COMPANY` (company→company) — **no artifact captured or parsed at all** for parent/subsidiary structure (would require 10-K Exhibit 21 or similar, which is not in the current parser surface). This is a missing-parser gap, not a missing-artifact gap — distinct from EDGE-07. **Disposed 2026-07-14 (Phase 7, 07-02): EXCLUDED — `capability_not_implemented`.** Confirmed via code reading: `resolvers/company.py`'s `_parent_company_entity_id` unconditionally returns `None` (no `_PARENT_CIK_KEYS` source column exists on `sec_company`). Machine-readable, fingerprinted in `edgar_warehouse/mdm/coverage.py:compute_edge08_has_parent_company_coverage`.
- [ ] **EDGE-09**: `EMPLOYED_BY` (person→company) — **source artifact: DEF 14A proxy filing documents** (feed `sec_executive_record`). **Root-caused 2026-07-13 (Phase 6, 06-06): ROOT-CAUSED / FIX DEFERRED, not populated.** Parser confirmed correct against real bronze content; the gap is that `_is_configured_parser_form` (`warehouse_orchestrator.py:1859`) never selects DEF14A/DEFA14A/8-K for the bulk artifact-fetch pipeline, so `sec_filing_attachment` is never populated for these forms at scale. Fix identified, not applied (fetch-volume/cost decision deferred). See `06-PHASE-CLOSURE-LEDGER.md`. **Not marked Complete** — the underlying relationship is still zero, only the zero state is now fully explained and documented, not silently unresolved.
- [x] **EDGE-10**: `AUDITED_BY` (company→audit_firm) — **source artifact: SEC companyfacts (XBRL entity-facts) API responses** (feed `sec_accounting_flag.auditor_pcaob_id`). **Disposed 2026-07-13 (Phase 6, 06-05): EXCLUDED — source-coverage exclusion (structural SEC API limitation).** The companyfacts aggregate API never surfaces `ix:nonNumeric` DEI facts for any company (confirmed across 3 unrelated filers + a control fact); `_derive_audited_by` is correct as-is. See `06-PHASE-CLOSURE-LEDGER.md`.
- [ ] **EDGE-11**: `INSTITUTIONAL_HOLDS` (adviser→security) — **source artifact: 13F-HR INFORMATION TABLE XML documents** (feed `sec_thirteenf_holding`). **Root-caused 2026-07-13 (Phase 6, 06-04/06-06): ROOT-CAUSED / FIX DEFERRED, not populated.** Shares its root cause with EDGE-09 (`_is_configured_parser_form` never selects 13F-HR for bulk artifact fetch: 0 of 48,877 filings have an attachment row). A real bronze-fetch fast-path bug was also found and fixed (`bronze_filing_artifacts.py`, committed + unit-tested), but that fix is downstream of the gate above and unreachable via the standard bulk pipeline. See `06-PHASE-CLOSURE-LEDGER.md`. **Not marked Complete** — fix committed but not deployed/graph-verified, and not yet reachable in bulk without the upstream gate fix.

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

- [x] **ARTF-01**: Silver-publishing warehouse commands (`parse-adv-bronze` and peers) never overwrite a healthier canonical `silver.duckdb` with a smaller/incomplete local copy — publish is skipped or guarded when the local copy would regress the canonical. **07-06**: `edgar_warehouse/silver_protection.py`'s fail-closed `PROTECTED_TABLE_REGISTRY` classifies every canonical domain table (business keys + provenance authority column) and explicitly excludes operational/checkpoint tables; `merge_candidate_into_canonical` never deletes a canonical-only row (a partial local candidate never regresses coverage), resolves same-key conflicts only via a table's declared authority column, and raises `SemanticMergeConflictError`/`SilverPublicationError` (row-level report) on ambiguous conflicts, unclassified tables, dropped columns, or column-type changes. `_publish_silver_database_if_remote` now merges into canonical (never overwrites it directly) before staged/promoted upload; there is no `--force` parameter anywhere on this path.
- [x] **ARTF-02**: Any newly-captured artifact fetch (from EDGE-09/EDGE-11 triage or elsewhere) honors SEC idempotency (DEC-009) — already-captured filings are not re-fetched without an explicit `--force`. **07-06**: added DEF 14A and 13F-HR cache-hit regression tests to `tests/unit/test_loader_idempotency.py` asserting `network_fetches == 0` and no download/get_filing calls (previously only ownership forms and 13F-HR *cold-start* were covered); `fetch_filing_artifacts`'s `force=True` path now emits a `repair_audit` entry (accession, prior/replacement object hash + storage version, operator, reason) whenever a real prior raw object is being replaced, threaded through `filing_artifact_service.refresh_filing_artifacts` via new optional `operator`/`reason` kwargs. **Caveat**: `operator`/`reason` are optional at the service boundary (not yet a required, validated CLI flag) so existing `warehouse_orchestrator.py`/`cli.py` `--force` call sites (outside this plan's declared file scope) keep working unchanged; they still get an honest audit record with `operator`/`reason` left `None` rather than a fabricated value. Wiring an explicit `--operator`/`--reason` CLI flag is a follow-up, not done here.

### Verified MDM → Neo4j Relationship Generations

- [x] **RPRE-01**: Before Phase 7 schema implementation, a live dev preflight using `SNOW_CONNECTION=snowconn` proves the Snowflake-hosted Neo4j Native App can load the contract views, expose typed date edge properties, execute supported graph metadata and BFS/multi-hop operations, and observe a stable-view test-generation switch. Required health uses documented stable operations plus semantic MDM↔graph parity; graph discovery uses the platform-owned generation registry. Experimental `LIST_GRAPHS` is informational and cannot independently block implementation. Verified GO on 2026-07-12 and human-approved.
- [ ] **RSYNC-01**: PostgreSQL MDM is the relationship derivation/staging authority, while both MDM serving reads and Snowflake-hosted Neo4j reads expose the same verified active generation. **Partial (07-03, 07-05)**: the transactional publication queue establishes MDM as the sole staging/request authority (07-03); 07-05 adds a real, guarded single-pointer Snowflake generation activation (`GRAPH_ACTIVE_POINTER`, `activate_graph_generation`/`rollback_graph_generation`). **Not done**: MDM's own serving reads (`api/routers/graph.py`) are not pinned to any generation concept -- they always read live/current Postgres state. This is architecturally intentional (MDM leads, the Snowflake graph follows on a verified lag) but is not literally "the same verified active generation" symmetrically exposed on both sides, so the requirement is not fully met as literally worded.
- [x] **RSYNC-02**: Each generation contains a complete node-and-edge snapshot and activates through one guarded Snowflake pointer only after identity-, property-, temporal-, endpoint-, and coverage-level verification passes for every registered type. **07-05**: additive per-generation `MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES` snapshots (Task 1); `HASH_AGG`-based exact identity/property parity across the full row content, including the typed temporal columns (Task 2, `_render_exact_node_parity`/`_render_exact_relationship_parity`); endpoint verification (`_render_missing_edge_endpoints` plus 07-04's `fan_in_generation` endpoint-gap check); `activate_graph_generation` refuses anything except `status == 'verified'`, and a failed/rejected activation is proven to leave the previous pointer's SQL completely unissued. **Caveat, not a full gap**: coverage-level exhaustiveness (07-02's `relationship_coverage` manifest) is enforced by `verify()` only when a caller explicitly supplies it to `SnowflakeGraphVerificationConfig` -- the live `mdm verify-graph` CLI invocation does not yet default to passing one (a pre-existing gap noted in 07-02's summary, not closed here). Marked complete because the mechanism itself is real and exhaustive when wired; the CLI-default wiring is a separate follow-up.
- [x] **RSYNC-03**: MDM commits graph-publication requests transactionally; a centralized publisher targets activation within five minutes, alerts after fifteen minutes, and never requires individual ingestion commands to implement graph synchronization. **07-03**: `mdm_publication_request` transactional outbox (`publication.request_publication`, same-session/rollback-atomic); `compute_publication_freshness` implements the exact 5-minute-warning/15-minute-hard-alert SLO (boundary-tested at 4:59/5:00/14:59/15:00) plus bounded-backfill-window exemption; `mdm publication-claim`/`publication-release-expired`/`publication-status` CLI coordinator entry points. Writers call `request_publication` only -- no Snowflake/Neo4j code in writer paths.
- [ ] **RSYNC-04**: Generation assembly fans out immutable type-first partitions in parallel, selectively hash-shards high-volume types, reuses content-addressed unchanged partitions, and independently retries failed partitions before fan-in. **Partial (07-04)**: `edgar_warehouse/mdm/generation.py` plans one partition per active node/relationship type (or N hash-sharded partitions via `sharding=`), computes a content address over `(kind, type, shard, mdm_watermark, rule_version, schema_version, input_fingerprint)`, reuses only exact content-hash matches against a prior `built` partition, and `fan_in_generation` rejects missing/duplicate shards, mixed watermarks/versions, endpoint gaps, and any non-built/reused partition. AWS orchestration (`generation_build` Step Functions state machine in `deploy-aws-application.sh`, Terraform-passive): `GenerationPlan` → bounded-concurrency (`MaxConcurrency`, default 8) `DISTRIBUTED` Map `BuildPartitions` (partition failures caught per-worker, `ToleratedFailurePercentage=100` so FanIn alone is pass/fail authority) → `FanIn` → `Activate` (only reachable via FanIn's success path, never its `Catch`) or `RetryFailedPartitions` (resets only `failed` partitions; `built`/`reused` partitions are inherited for free on the next attempt via content-hash reuse). New MDM writes queue independently through the 07-03 publication outbox the whole time -- no lock/constraint couples `mdm_publication_request` to `mdm_graph_generation`/`mdm_graph_partition`, confirmed by `TestConcurrentGenerationsNotBlocked`. **Not done**: the actual per-partition Snowflake row write (this module's `build_partition` only advances MDM-side manifest state; the real `SnowflakeGraphSyncExecutor` write and the `Activate` step's guarded Snowflake pointer flip are 07-05's scope), and `generation_build` is not yet chained into `load_history`/`bootstrap`/`daily_incremental` (deferred to whichever plan wires the shared activation pointer those pipelines read).
- [x] **RSYNC-05**: Failed/incomplete generations never become visible; the prior verified generation remains active, and rollback can select a retained verified generation. Retention keeps at least three generations and all generations from the prior 30 days. **07-05**: `activate_graph_generation` refuses (no SQL executed) any generation whose status isn't `'verified'`, guaranteeing failed/incomplete generations can never become visible and a rejected activation leaves the previous pointer untouched; `rollback_graph_generation` accepts only `'activated'`/`'retired'` (i.e. previously verified+live) targets; `cleanup_retired_generations`/`render_cleanup_candidates` retain the newest 3 retired generations (which always includes the immediate predecessor of the current active one, since it retires most recently) plus every generation created within the last 30 days, and never touch `'building'`/`'verified'`/`'activated'`/`'failed'` rows.
- [x] **RTEMP-01**: Relationships have stable logical and version identifiers plus date-only `[valid_from_date, valid_to_date)` validity, explicit date provenance, and synchronized typed temporal properties in MDM and Neo4j. **Partial (07-01)** → **Complete (07-05)**: `render_graph_tables` now stages `RELATIONSHIP_ID`, `VALID_FROM_DATE`, `VALID_TO_DATE`, and `DATE_PROVENANCE` onto every `MDM_GRAPH_EDGES` row and every per-type `GRAPH_EDGE_*` view, closing the gap 07-01 explicitly flagged ("the new temporal columns are not yet synchronized to the Snowflake-hosted Neo4j graph").
- [x] **RTEMP-02**: Active graph generations retain complete non-quarantined relationship history; strict `as_of_date` traversal excludes temporally unproven edges unless uncertainty is explicitly requested and labeled. **07-05 Task 3**: `api/routers/graph.py`'s `neighborhood`/`traversal` now filter on `valid_from_date`/`valid_to_date`/`date_provenance` (not the legacy `effective_from`/`effective_to`), half-open inclusive-start/exclusive-end, `date_provenance == 'unknown'` excluded by default and only surfaced (labeled `date_uncertain: true`) via explicit `include_unknown_dates=True`. As-of-date queries deliberately drop the `is_active` filter (querying `quarantined == False` instead) so a since-superseded version is found when it was the version actually valid at that past date -- the no-`as_of` "current" default still filters to `is_active == True` only, unchanged.
- [x] **RTEMP-03**: Direct relationships remain authoritative in MDM; multi-hop paths are queried in Neo4j, while materialized derived edges require deterministic rules, provenance, freshness policy, and an explicit derived label. **07-01**: `relationship_kind` (`direct`/`derived`) added.
- [x] **RTEMP-04**: Conflicting temporal overlaps follow relationship-specific source-priority/tie-break policies; unresolved conflicts are quarantined and block activation. Ordinary workflows never physically delete relationship history. **07-01**: `mdm_relationship_source_priority` table + `ensure_relationship`'s supersede/quarantine conflict policy; no delete function exists anywhere in `graph.py` (regression-tested).
- [x] **RCOV-01**: Every registered relationship type has exactly one per-generation coverage status: `populated`, freshly-proven `valid_zero`, or current-evidence `excluded`; any missing, stale, contradictory, or undocumented status blocks activation. **07-02**: `compute_relationship_coverage_manifest`/`verify_relationship_coverage_manifest` (coverage.py) classify all 11 active relationship types exhaustively and fail closed on missing/stale/contradictory/nonzero-excluded records.
- [x] **RCOV-02**: EDGE-07 is machine-readably classified `source_unavailable` and EDGE-08 `capability_not_implemented`, each with relationship-specific evidence fingerprints and no synthetic graph edges. **07-02**: `compute_edge07_manages_fund_coverage`/`compute_edge08_has_parent_company_coverage`.
- [x] **RLINE-01**: Entity merges remap graph traversal to the surviving canonical entity while preserving original source identity and merge lineage; edge IDs and relationship-version IDs remain stable across generations. **Partial (07-01)** → **Complete (07-05)**: relationship-version-ID stability was already real (`relationship_id`/`instance_id` deterministic and immutable). 07-05 adds the entity-merge remap `merge_entities()` never did: a bounded (5-hop) merge-lineage resolution in both the Snowflake-staged graph (`GRAPH_ENTITY_MERGE_LINEAGE` view over `MDM_CHANGE_LOG`'s `merged_from` records; staged edges carry canonical `SOURCENODEID`/`TARGETNODEID` plus original `SOURCENODEID_ORIGINAL`/`TARGETNODEID_ORIGINAL`) and the live FastAPI `neighborhood`/`traversal` endpoints (`_canonical_groups`/`_canonicalize` in `api/routers/graph.py`; `GraphNode.merged_from` lists every raw id canonically resolved to that node, `GraphEdge.source_entity_id_original`/`target_entity_id_original` preserve provenance). Verified: querying either the kept or the discarded entity_id finds the same connected edge; a multi-hop path through a merged entity remains connected.

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
| EDGE-05 | Phase 6 | Complete (excluded — see 06-PHASE-CLOSURE-LEDGER.md) |
| EDGE-06 | Phase 6 | Complete (excluded — see 06-PHASE-CLOSURE-LEDGER.md) |
| EDGE-09 | Phase 6 | Root-caused; fix deferred (see 06-PHASE-CLOSURE-LEDGER.md) |
| EDGE-10 | Phase 6 | Complete (excluded — see 06-PHASE-CLOSURE-LEDGER.md) |
| EDGE-11 | Phase 6 | Root-caused; fix deferred (see 06-PHASE-CLOSURE-LEDGER.md) |
| EDGE-07 | Phase 7 | Complete (excluded — see 07-02-SUMMARY.md) |
| EDGE-08 | Phase 7 | Complete (excluded — see 07-02-SUMMARY.md) |
| ARTF-01 | Phase 7 | Complete (07-06) |
| ARTF-02 | Phase 7 | Complete (07-06, CLI-flag wiring caveated) |
| RPRE-01 | Phase 7 | Complete |
| RSYNC-01 | Phase 7 | Partial (07-03, 07-05 — Snowflake single-pointer activation is real; MDM serving reads remain live/current, not generation-pinned) |
| RSYNC-02 | Phase 7 | Complete (07-05 — exact identity/property/temporal/endpoint verification + guarded activation; coverage-exhaustiveness needs an explicit manifest, not yet CLI-default) |
| RSYNC-03 | Phase 7 | Complete (07-03) |
| RSYNC-04 | Phase 7 | Partial (07-04 — partition planning/reuse/fan-in + AWS fan-out orchestration; per-partition Snowflake row write pending future work) |
| RSYNC-05 | Phase 7 | Complete (07-05) |
| RTEMP-01 | Phase 7 | Complete (07-05 — new temporal columns now synced to the Snowflake-hosted graph) |
| RTEMP-02 | Phase 7 | Complete (07-05) |
| RTEMP-03 | Phase 7 | Complete (07-01) |
| RTEMP-04 | Phase 7 | Complete (07-01) |
| RCOV-01 | Phase 7 | Complete (07-02) |
| RCOV-02 | Phase 7 | Complete (07-02) |
| RLINE-01 | Phase 7 | Complete (07-05 — canonical merge remap in both Snowflake staged graph and live FastAPI traversal) |
| GVER-01 | Phase 8 | Complete |
| GVER-02 | Phase 8 | Complete |
| EDGX-01 | Phase 9 | Pending |
| EDGX-02 | Phase 9 | Pending |
| EDGX-03 | Phase 9 | Pending |
