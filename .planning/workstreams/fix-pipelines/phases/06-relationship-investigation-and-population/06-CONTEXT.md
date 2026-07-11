# Phase 6: Relationship Investigation And Population - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Root-cause why `IS_ENTITY_OF`, `IS_PERSON_OF`, `EMPLOYED_BY`, `AUDITED_BY`, and
`INSTITUTIONAL_HOLDS` sit at zero rows, and populate whichever the investigation shows are
unblocked. Every relationship type investigated must exit this phase with either nonzero
graph-verified rows or a written, evidenced source-coverage exclusion — no type exits in an
undocumented zero state. Requirements: EDGE-05, EDGE-06, EDGE-09, EDGE-10, EDGE-11.

</domain>

<decisions>
## Implementation Decisions

### Real-data prerequisite (EDGE-09/EDGE-10/EDGE-11 data availability)

- **D-01:** Investigate the 2026-07-06 `bootstrap` Step Function failure first (5-whys root
  cause, per CLAUDE.md's debugging discipline) before running `load_history`. `load_history`
  itself has **zero executions ever** in dev (`690839588395`) — confirmed via
  `aws stepfunctions list-executions`. Its one exercised sibling (`bootstrap`) failed as
  recently as 2026-07-06 with the root cause not yet established; running a bigger, more
  expensive operation on top of an unexplained failure risks compounding an unknown issue.
- **D-02:** Trigger a bounded `load_history` execution in dev at **~100-200 companies** as
  part of Phase 6 (not a follow-on operator action). This is a deliberate user override of the
  advisor-research recommendation, which favored investigating against dev's existing dataset
  first (MDM Postgres already holds 15,285 nodes / 1,117 edges, confirmed stable across reruns
  during Phase 5's GVER-03 work) and treating a proving-run as a follow-on step — mirroring how
  Phase 5 treated `EDGARTOOLS_PRODB` replication. User explicitly chose to load more data now.
  ~100-200 companies matches CLAUDE.md's documented example scale (~15 min runtime via
  parallel ECS batches for 100 companies) — enough breadth to likely surface DEF 14A / 13F /
  XBRL coverage for EDGE-09/10/11 without full-active-universe cost/time.
- Context: all three Branch B `bootstrap-fundamentals` modes needed for these relationship
  types are already correctly wired sequentially into the state machine
  (`Stage1BEntityFacts → Stage1BPerFiling → Stage1BThirteenF → MdmRun`, confirmed via
  `tests/architecture/test_load_history_state_machine.py`) — this is a **never-run-at-scale**
  gap, not a missing-integration gap. No pipeline wiring fix is needed here.
- Context: Codex's `fundamental-factors-v2` workstream is currently on Phase 3
  (cash-conversion-cycle, gold-dbt-layer-only — "no new loader, no new SEC fetch path, only
  silver/gold changes" per its own STATE.md). It does not touch `bootstrap_fundamentals.py`,
  `accounting_flags.py`, `proxy_fundamentals.py`, or `thirteenf.py`. The standing "coordinate
  before running fundamentals in dev" caution (PROJECT.md) still applies procedurally, but the
  actual overlap risk with Codex's current active work is low — running `bootstrap-fundamentals`
  does not touch any file Codex's Phase 3 plans modify.

### INSTITUTIONAL_HOLDS batching (EDGE-11)

- **D-03:** Implement the CIK-range batched-read strategy in `_derive_institutional_holds` now
  (per the existing TODOS.md design: `WHERE cik BETWEEN ? AND ?` in configurable increments,
  e.g. ~1000 CIKs/batch — tune based on actual `sec_thirteenf_holding` row density observed in
  dev once loaded), not deferred to a later pass. This is a deliberate user override of the
  advisor-research recommendation, which favored shipping the existing bounded/`remaining`-param
  version now and deferring batching until a full-universe run was actually scheduled. Given
  D-02 puts a real `load_history` run in this phase, the OOM risk TODOS.md flagged ("design a
  batched-read strategy before writing the Phase 6 full-universe sync plan") is now live, not
  hypothetical — building it now is consistent with D-02, not premature.
- Adviser-entity resolution in this deriver is per-CIK, so CIK-range chunk ordering carries no
  correctness risk (per TODOS.md's own analysis) — this deriver is safely batchable.

### Adviser-link closure bar (EDGE-05, EDGE-06)

- **D-04:** Close EDGE-05 (`IS_ENTITY_OF`) and EDGE-06 (`IS_PERSON_OF`) via a SQL-confirmed
  zero-overlap check against the loaded MDM universe: `MdmCompany.cik` ∩ `MdmAdviser.cik` for
  EDGE-05; `MdmPerson.owner_cik` ∩ `MdmAdviser.cik` for EDGE-06. This uses the exact same
  CIK-keyed join logic `AdviserResolver._link_to_company` and
  `pipeline.py:_adviser_person_pairs()` already run in production — the SQL check is not a
  weaker proxy, it independently verifies what the resolver already computes. Any resulting
  exclusion must be documented as scoped to "as of the current tracking-list universe," not the
  full SEC registrant population — re-check required if the tracking list expands.
- Context: `AdviserResolver.resolve_one` already calls `_link_to_company` on every adviser
  resolution (`edgar_warehouse/mdm/resolvers/adviser.py:109`) — this resolver step is
  confirmed NOT dormant; it runs automatically. Zero rows most likely reflects a genuine
  "no CIK overlap in this universe" data fact, not a broken/missing step.
- A manual EDGAR full-text-search audit (spot-checking advisers against SEC filings outside
  the loaded universe) was considered and explicitly not chosen — it answers a different
  question (universe-selection completeness) that belongs to a separate workstream, not this
  relationship-investigation phase.

### Neo4j relationship counting (cross-cutting, all types Phase 6 populates)

- **D-05:** For each relationship type Phase 6 confirms populated, extend
  `POPULATED_RELATIONSHIP_TYPES` and add a named parity check in
  `edgar_warehouse/mdm/snowflake_graph.py`, mirroring 05-03's exact pattern — keeping
  `verify-graph` the single atomic gate consumed by both the Step Functions `mdm_verify_graph`
  state and `go-live.sh`'s local preflight (per Phase 5's D-01, which explicitly ruled out a
  second/parallel verification command). "Graph-verified rows," not just MDM-side counts, is
  what ROADMAP.md's Phase 6 closure bar actually requires.
- Sequencing note for planning: for each newly-populated type, MDM relationship derivation
  must run, THEN `mdm sync-graph` must run, THEN `verify-graph` will find graph-side rows for
  it. Adding a type to `POPULATED_RELATIONSHIP_TYPES` before `mdm sync-graph` has run for it
  will correctly fail closed (expected behavior per 05-03's design, not a bug) — plans must
  sequence derive → sync → verify per type, not discover this as a surprise failure.

### Claude's Discretion

- Exact CIK-range batch size for INSTITUTIONAL_HOLDS batching (D-03) — TODOS.md suggests
  ~1000 CIKs as an example; tune based on real `sec_thirteenf_holding` row density once the
  bounded `load_history` run (D-02) actually lands data.
- Whether the bounded `load_history` run (D-02) uses `--tracking-status-filter active` or a
  specific `--cik-list`/limit flag — pick based on whichever surfaces the broadest DEF 14A /
  13F / XBRL coverage for EDGE-09/10/11.
- Ordering of investigation within Phase 6's plan waves (e.g., root-causing the prior
  `bootstrap` failure and running `load_history` are logical prerequisites for EDGE-09/10/11
  work; the EDGE-05/06 SQL check and EDGE-11 batching code have no dependency on the load and
  could proceed in parallel).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements and roadmap
- `.planning/workstreams/fix-pipelines/REQUIREMENTS.md` — full EDGE-05, EDGE-06, EDGE-09,
  EDGE-10, EDGE-11 requirement text
- `.planning/workstreams/fix-pipelines/ROADMAP.md` — Phase 6 goal, success criteria,
  dependency on Phase 5 (complete)

### MDM relationship derivation
- `edgar_warehouse/mdm/pipeline.py` — `_derive_is_entity_of` (~L662), `_derive_is_person_of`
  (~L709), `_derive_employed_by` (~L1114), `_derive_audited_by` (~L1214),
  `_derive_institutional_holds` (~L1330), `_adviser_company_pairs` (~L1438),
  `_adviser_person_pairs` (~L1446), `_fetch_optional_relationship_rows` (~L121),
  `_bounded_relationship_sql` — the limit-bounded fetch mechanism D-03's batching extends
- `edgar_warehouse/mdm/resolvers/adviser.py` — `AdviserResolver.resolve_one` (~L50),
  `_link_to_company` (~L167) — confirmed-active `linked_company_entity_id` resolver

### Source artifact parsers (Branch B / bootstrap-fundamentals)
- `edgar_warehouse/application/commands/bootstrap_fundamentals.py` — 3 modes: `per-filing`
  (DEF 14A → `sec_executive_record`, EDGE-09), `entity-facts` (SEC companyfacts API →
  `sec_accounting_flag`, EDGE-10), `thirteenf` (13F-HR → `sec_thirteenf_holding`, EDGE-11)
- `edgar_warehouse/parsers/proxy_fundamentals.py` — DEF 14A parser
- `edgar_warehouse/parsers/accounting_flags.py` — 10-K XBRL DEI auditor parser (PCAOB ID) +
  forensic-score backfill
- `edgar_warehouse/parsers/thirteenf.py`, `edgar_warehouse/scripts/build_13f_filer_list.py` —
  13F-HR INFORMATION TABLE parser
- `edgar_warehouse/application/workflows/fundamentals_ingest.py` — fundamentals orchestration

### Pipeline wiring verification
- `tests/architecture/test_load_history_state_machine.py` (~L202-234) — proves
  `Stage1Parallel → Stage1BEntityFacts → Stage1BPerFiling → Stage1BThirteenF → MdmRun`
  sequential wiring already exists and is correct

### Neo4j graph verification (Phase 5 pattern D-05 extends)
- `edgar_warehouse/mdm/snowflake_graph.py` — `POPULATED_RELATIONSHIP_TYPES` (~L39),
  `_named_node_parity_checks` (~L1193), `_named_relationship_parity_checks` (~L1227)
- `.planning/workstreams/fix-pipelines/phases/05-node-and-populated-relationship-graph-parity/05-CONTEXT.md`
  — D-01 (single-gate decision, do not create a second verify command)

### Known documented gaps
- `TODOS.md` (~L8-33) — "INSTITUTIONAL_HOLDS full-universe sync: batch-by-CIK-range to avoid
  OOM" — the design D-03 implements
- `TODOS.md` (~L582-606) — T1 (bootstrap-fundamentals S3-upload fix, RESOLVED 2026-06-17), T6
  (single-CIK Apple/320193 proof, RESOLVED 2026-06-13) — prior evidence the pipeline works
  end-to-end for one CIK, not yet at active-universe scale

### Operator/deploy tooling and standing constraints
- CLAUDE.md — "Phased Pipeline" section (`load_history` usage, timing), "Debugging
  discipline: 5-whys" section (governs D-01), DEC-009 (SEC idempotency — any newly-fetched
  artifact must skip already-captured filings by default)
- `.planning/workstreams/fundamental-factors-v2/STATE.md` — Codex's current Phase 3 scope
  (gold-dbt-layer-only), informs the lowered EDGE-10 coordination risk assessment above

### Documentation debt flagged (not blocking Phase 6, for awareness)
- `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md` is cited by REQUIREMENTS.md
  and 05-CONTEXT.md (EDGE-07 exclusion evidence) but currently lives only on the unmerged
  `claude/mdm-source-recovery` branch (commit `3d28a01`), not on `claude/fix-pipelines-v2`.
  Dangling reference — a Phase 7 concern (EDGE-07 documentation), not Phase 6's.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_fetch_optional_relationship_rows` / `_bounded_relationship_sql` (`pipeline.py`) — the
  existing limit-bounded fetch mechanism already used by all 3 artifact-backed derivers
  (EMPLOYED_BY, AUDITED_BY, INSTITUTIONAL_HOLDS); D-03's CIK-range batching extends this
  pattern, it doesn't replace it.
- `POPULATED_RELATIONSHIP_TYPES` + `_named_relationship_parity_checks()`
  (`snowflake_graph.py`, built in 05-03) — the exact pattern D-05 extends per newly-populated
  type.
- `ensure_relationship(...)` upsert pattern via `sync_engine` — idempotent by construction,
  the same pattern GVER-03 (Phase 5) already proved with committed regression tests; any new
  Phase 6 derivation work should follow it without re-deriving idempotency from scratch.

### Established Patterns
- MDM relationship derivation reads from the **silver DuckDB** (`self.silver.fetch(...)`), not
  from Snowflake `EDGARTOOLS_SOURCE`. Confirmed by tracing `_fetch_optional_relationship_rows`.
  The native-S3-pull → `EDGARTOOLS_SOURCE` → dbt → `EDGARTOOLS_GOLD` path (currently empty in
  the freshly-rebuilt dev Snowflake trial account) is a separate, unrelated data path — not a
  Phase 6 blocker, since none of the 5 target derivers read from it.
- Graph sync (`mdm sync-graph`) is a full-rebuild (`CREATE OR REPLACE TABLE ... AS SELECT`)
  from current MDM Postgres state — D-05's sequencing note (derive → sync → verify) follows
  directly from this: a type isn't graph-visible until the next full sync runs.

### Integration Points
- `verify()`'s pass/fail gate in `snowflake_graph.py` — where each `POPULATED_RELATIONSHIP_TYPES`
  addition (D-05) plugs in.
- Step Functions `mdm_verify_graph` state, `go-live.sh`'s `run_hosted_graph_preflight` — both
  consume `verify-graph` directly; D-05 must not fragment this single gate.
- `load_history` Step Function (`arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-load-history`)
  — the D-02 bounded run's target; zero prior executions, so this phase is also the first
  real-world exercise of this state machine.

</code_context>

<specifics>
## Specific Ideas

- User explicitly overrode the advisor research's recommendation on two of four areas: chose
  to run a real bounded `load_history` load now (D-02) rather than defer, and chose to build
  the INSTITUTIONAL_HOLDS CIK-range batching now (D-03) rather than defer — both push Phase 6
  toward "prove it works at real, if bounded, scale" rather than "investigate against whatever
  already exists." Plans should size accordingly (this phase carries real AWS/SEC-API
  execution time, not just code changes).
- Root-causing the 2026-07-06 `bootstrap` Step Function failure before running `load_history`
  (D-01) was Claude-initiated per CLAUDE.md's own 5-whys debugging discipline — the user did
  not push back when this was proposed alongside the load-scale question, so treat it as
  confirmed, not optional.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 6 scope. No scope-creep suggestions arose during this
session's discuss-phase.

### Reviewed Todos (not folded)

None — `todo.match-phase 6` returned zero matches. (Note: `TODOS.md`'s "INSTITUTIONAL_HOLDS
full-universe sync" entry was found via manual grep, not the automated matcher — it directly
informed D-03 above and is listed in canonical_refs, effectively folded despite the matcher
miss.)

</deferred>

---

*Phase: 6-relationship-investigation-and-population*
*Context gathered: 2026-07-08*
