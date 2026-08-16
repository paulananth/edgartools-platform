# Extend Sharded Silver Writes to Primary Ingestion

Label: `wayfinder:map`

## Destination

An implementation-ready plan for extending the already-proven sharded write
path (`_hydrate_shard_for_window`/`_publish_shard_if_remote`, currently wired
to exactly one command — `bootstrap-batch` with an explicit `cik_list`) to
`load_history`'s `WindowedBootstrap` and `bootstrap_fundamentals.py`'s three
Stage 1B modes (`entity-facts`/`per-filing`/`thirteenf`) — so canonical
silver storage stops being a single file that gets fully `shutil.copy2()`'d
and re-uploaded on every publish, for the two surfaces that actually caused
this effort's originating incidents. Reaching the end of this map means
someone can start implementing without hitting an undecided design question:
shard-routing mechanics per surface, downstream consumer (gold-refresh,
MDM's `ShardedSilverReader`, 5 ops scripts, 2 validation tools) migration,
migration/cutover safety, and rollout sequencing are all settled.
`daily_incremental`/`bootstrap` are explicitly out of scope — see below.

**Scope correction #1 (ticket 02's finding):** `bootstrap_fundamentals.py:135`
(the Stage 1B fundamentals writer — `load_history`'s `FetchEntityFacts`/
`FetchPerFilingFundamentals`/`FetchThirteenFHoldings`, the exact commands
whose `ToleratedFailurePercentage` was fixed earlier the same session as
this map was charted) writes the monolith directly and bypasses shard
routing entirely today. This is a **fourth primary-write surface**, not
named in the Destination above when this map was first charted — it must be
covered by this map's decisions, not treated as `WindowedBootstrap`'s
plumbing by assumption. See ticket 07.

**Scope correction #2 (narrowed during ticket 05's grilling, once tickets
01/02/03/07 made the real cost of each surface concrete):** the Destination
is narrowed to **only `WindowedBootstrap` (`bootstrap-next`) and
`bootstrap_fundamentals.py`'s three modes**. Both are proven-pattern,
moderate-effort (tickets 01, 07), and are exactly the two surfaces that
caused both live incidents this whole effort started from. `daily_incremental`
and `bootstrap`'s default invocation are **removed from this map's
destination** — ticket 01 found they're structurally cross-shard per run,
needing genuinely new multi-shard-write engineering that doesn't exist
anywhere in this codebase, not a reuse of the proven pattern. See "Out of
scope" below for the full rationale; this is a redrawn destination, not an
abandoned one — `daily_incremental`/`bootstrap` remain a legitimate future
map once the two-surface rollout here has proven the pattern in prod.

## Notes

- Grounding research, already done, do not re-derive:
  [`aws-steady-state-cost-and-silver-size-2026-08-14.md`](../ecs-cost-sizing/research/aws-steady-state-cost-and-silver-size-2026-08-14.md)
  (silver.duckdb is ~1.5GB current size; sharded write path exists in
  `warehouse_orchestrator.py`'s Phase 9 STORE-02/03 but gated to
  `bootstrap-batch` only; every primary ingestion command still
  `shutil.copy2()`s the whole file via `merge_candidate_into_canonical`;
  `ShardedSilverReader` is read-only; Snowflake's `EDGARTOOLS_SOURCE` mirrors
  only ~25 of ~39 silver tables, DuckDB remains the actual merge engine).
- Two live incidents this same architecture already caused, both patched
  independently of this map: OOM kills on Stage1B entity-facts/per-filing
  (ecs-cost-sizing ticket 20, fixed via a phase-1-SQL/phase-2-chunked merge
  rewrite) and ~$1.05-1.13/day of S3 noncurrent-version waste
  (ecs-cost-sizing ticket 22, fixed via an S3 lifecycle rule). This map is
  about the underlying pattern those two patched around, not a re-litigation
  of either fix.
- **Locked scope, from the initial grilling round**: extend the *existing*
  CIK-range sharded write path (Option A from the cost research). Eliminating
  DuckDB entirely in favor of Snowflake-as-sole-canonical-store (Option C)
  and inventing a new form-type partitioning axis (Option B) are both **out
  of scope** — see below.
- Priority across correctness/OOM-risk-at-scale, further AWS cost reduction,
  and operational simplicity is roughly equal — no single axis should
  dominate ticket decisions at the expense of the others.
- **Aiming to act soon** — unlike the planning-only `ecs-cost-sizing` map,
  this effort should reach an implementation-ready decision promptly, not
  sit indefinitely. Once the frontier clears, expect a follow-up
  implementation session.
- Every `grilling` ticket here: always invoke `/grilling` and
  `/domain-modeling`, per the wayfinder skill's ticket-type default.
- Before implementation starts (a later effort, not this map): consult
  `/gof-refactor-reviewer` per this repo's CLAUDE.md standing instruction.
- This repo has a documented history of subtle correctness regressions from
  getting silver-publish/sharding/concurrency assumptions wrong (CLAUDE.md's
  "INSTITUTIONAL_HOLDS/EMPLOYED_BY", "Manifest-pipeline ownership +
  cursor-syntax incident" 5-whys) — every design ticket on this map should
  weigh that history explicitly, not just theoretical risk.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- [Decide Rollout Sequencing and Safety Gate](issues/05-decide-rollout-sequencing-and-safety-gate.md) — also settled the map's Scope correction #2 (`daily_incremental`/`bootstrap` removed from destination). `WindowedBootstrap`/`bootstrap_fundamentals.py` ship together (no smaller subset to sequence). `sec_raw_object`/`sec_company_filing` (the only two risky tables actually in the narrowed scope) get full replication, like the ADV global tables — resolves their 3 dependent tables automatically. Monolith retention: migrate every consumer first, then cut over cleanly (not dual-write). Safety gate: shadow/dry-run with N consecutive clean diffs, reusing `migrate_silver_shards.py`'s existing 3-layer verification.

- [Confirm PROTECTED_TABLE_REGISTRY's Business-Key Uniqueness Never Crosses Shard Boundaries](issues/03-confirm-no-business-key-crosses-shard-boundaries.md) — 14/31 tables are safe under CIK-range sharding as routed today; 9 more are unrouted gaps trivially safe to add; but `sec_raw_object` (content-hash key, CIK is provenance-only) and `pipeline_run_lease` (mutual-exclusion lock) need real design decisions, plus 6 more tables (`sec_company_filing`, `sec_current_filing_feed`, `sec_subsidiary_evidence`, `sec_auditor_report_evidence`, `sec_employment_event`, `sec_adv_firm_roster`/`sec_pcaob_firm_identity`) carry either the same multi-registrant-accession risk or have no CIK affinity at all.

- [Confirm Downstream Consumer Compatibility With N Shards](issues/02-confirm-downstream-consumer-compatibility.md) — gold-refresh and all of `GOLD_AFFECTING_COMMANDS`, `validate_data_quality.py`, `verify_pipeline_run.py`, and 5 ops scripts all read the monolith directly today (not `ShardedSilverReader`); shard count itself is fully dynamic everywhere except a hardcoded `!=4` check in the one-time `migrate_silver_shards.py`; monolith must stay written (not retired) until all of these are migrated.

- [Confirm Shard-Routing Mechanics Are Reusable As-Is for Primary Ingestion Commands](issues/01-confirm-shard-routing-reusable-for-primary-commands.md) — routing is trivial reuse only for `load_history`/`bootstrap-next` (moderate plumbing: wire it to read the already-written `cik_snapshot.jsonl` before DB-open, same shape as `bootstrap-batch`'s existing `seed-bronze-batches` pattern); `daily_incremental` and `bootstrap`'s default invocation are structurally cross-shard per run (impacted/active CIKs span all bands, no single-owner-per-shard guarantee), needing genuinely new multi-shard write plumbing, not a routing lookup — and the sharded publish path bypasses `merge_candidate_into_canonical` entirely today (single-owner ETag promote instead), so any command spanning shards needs a real shard-aware merge that doesn't exist yet.

- [Confirm Shard-Routing Requirements for bootstrap_fundamentals.py's Stage 1B Writer](issues/07-confirm-bootstrap-fundamentals-shard-routing.md) — `bootstrap_fundamentals.py` never touches the shard path (zero `shard`/`_using_shard_path` references) and publishes through the same monolith `merge_candidate_into_canonical` call as `bootstrap-next`; it has the identical chicken-and-egg CIK-resolution gap (`cik_snapshot.jsonl` exists before DB-open but isn't read, re-derived instead from an already-open DB), but is trivially the *same* fix as ticket 01's, and simpler to trust, since all three windowed modes' reads are provably scoped to `WHERE cik IN (this window's own cik_list)` against CIK-direct/issuer-CIK-join tables — no cross-shard read requirement like `daily_incremental`/`bootstrap`.

## Not yet specified

- Whether any change here needs to coordinate with the still-unfixed
  `WindowedBootstrap`/`_capture_submission_bronze_snapshots` memory-
  accumulation gap (noted as residual risk earlier this session, separate
  bug, not yet its own ticket anywhere) — revisit once the shard-routing
  research (tickets 01-03) clarifies whether sharding changes that code
  path's memory profile at all.
- Exact resharding mechanics if a future universe size outgrows 4 shards —
  ticket 06 below scopes whether this is answerable now or stays fog.

## Out of scope

- **Eliminate DuckDB entirely, Snowflake becomes sole canonical store**
  (research's Option C) — explicitly ruled out in this map's initial
  grilling round. Porting `silver_protection.py`'s entire business-key
  merge/conflict-resolution engine into Snowflake SQL was judged too large
  and too risky relative to the "act soon" timeline; Snowflake's
  `EDGARTOOLS_SOURCE` schema is also not a full replica today (~25 of ~39
  tables), which would itself be a prerequisite before Option C could even
  be attempted.
- **New form-type partitioning axis** (research's Option B) — the chosen
  direction extends the *existing* CIK-range sharding mechanism (already
  proven via `bootstrap-batch`), not a new partitioning scheme. If CIK-range
  sharding later proves insufficient on its own, form-type partitioning
  remains a candidate for a future, separate effort — not ruled out forever,
  just not this map's destination.
- **`daily_incremental` and `bootstrap`'s sharded write path** — removed
  from this map's destination during ticket 05's grilling (Scope correction
  #2 above), once ticket 01 found they're structurally cross-shard per run
  and would need genuinely new multi-shard-write engineering, unlike
  `WindowedBootstrap`/`bootstrap_fundamentals.py`'s reuse of the proven
  `bootstrap-batch` pattern. Not ruled out forever — a legitimate future map
  once this one's two-surface rollout has proven the pattern live in prod —
  just not this map's destination, consistent with "aiming to act soon"
  favoring the safe high-value slice over solving the hardest 20% before
  shipping anything.
- **`pipeline_run_lease`, `sec_adv_firm_roster`, `sec_pcaob_firm_identity`,
  `sec_subsidiary_evidence`, `sec_auditor_report_evidence` shard-boundary
  handling** — confirmed during ticket 05's grilling to be irrelevant to the
  narrowed destination: `pipeline_run_lease` belongs to Daily Identity
  Refresh (`daily_incremental`/`bootstrap`'s stage, now out of scope
  itself); the two ADV tables belong to the separate `FetchAdvBulk`
  pipeline; the two evidence tables have no confirmed caller anywhere in
  the codebase today (0 rows in the live Snowflake mirror). Out of scope
  here, not because they're unimportant, but because neither
  `WindowedBootstrap` nor `bootstrap_fundamentals.py` touches them.
