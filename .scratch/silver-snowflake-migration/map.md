# Silver-on-Snowflake Migration

## Destination

Silver's canonical store moves fully off S3/local-DuckDB and onto Snowflake:
a locked target architecture (Python-populated Snowflake landing zone for
SEC-document parsing, feeding dbt-native silver transformation models) plus
a staged migration plan from today's monolithic `silver.duckdb`-on-S3 state.
Done when someone can implement the migration without further architecture
debate — this map does not implement it.

## Notes

- Domain: `edgar_warehouse/silver_store.py` (4,360 lines — the real bulk of
  today's write/merge/promotion logic; `silver.py` itself is now just a
  7-line compatibility shim), `edgar_warehouse/silver_support/
  sharded_reader.py`, `edgar_warehouse/silver_protection.py` (967 lines,
  canonical merge/promotion), `edgar_warehouse/serving/gold_models.py`
  (Python gold builders reading silver's DuckDB connection directly via raw
  SQL), `edgar_warehouse/mdm/` sharded silver reads, `edgar_warehouse/
  parsers/` (`ownership.py`, `adv.py` — Python-only SEC document parsing via
  the `edgartools` package; this does not move to SQL, see below),
  `infra/snowflake/dbt/edgartools_gold/` (existing dbt project this
  migration extends with a new silver layer).
- **Settled scope, from this session's destination-naming/frontier-mapping
  grilling** (captured here since no tickets existed yet to hold them):
  - Full rewrite of the query/transform layer to Snowflake — not a
    storage-swap that keeps DuckDB as the local query engine.
  - Shape: dbt-native. A new Python-populated Snowflake landing zone holds
    parsed-but-not-yet-cleaned rows; dbt silver models (clean/dedupe/merge)
    sit between that landing zone and gold, replacing most of
    `silver_store.py`'s custom Python merge/promotion/ETag-optimistic-
    concurrency machinery with Snowflake's native `MERGE`/transactions.
  - **Refinement, not optional**: Python (via the `edgartools` package,
    confirmed live — `edgar_warehouse/parsers/ownership.py` imports
    `edgar.ownership.Ownership` directly) still does all SEC-document
    parsing (XBRL, ownership Form 3/4/5, ADV). That step is fundamentally
    Python's job and does not become dbt/SQL under any version of this
    migration — only the clean/dedupe/merge logic downstream of parsing
    moves to dbt.
  - Standing requirement: every provisioning step in this migration is a
    committed, re-runnable script — never a manual/uncommitted session —
    and ownership goes to one dedicated loader role from day one. Direct
    lesson from this repo's own documented incidents: the MDM Snowflake
    mirror schema was silently lost because it was provisioned by an
    uncommitted manual session; a later `GRANT OWNERSHIP ... REVOKE CURRENT
    GRANTS` step separately stripped an unrelated role's grants. Both are
    in CLAUDE.md under "MDM Snowflake mirror schema lost on cutover" and
    "Manifest-pipeline ownership + cursor-syntax incident" — read before
    drafting Ticket 05's checklist.
  - **Sequencing: `load_history`'s retry6 (ticket 42's full-universe
    backfill) is blocked on this map** — specifically on
    [Design the Snowflake-Native Silver Layer's Model Structure](issues/01-design-snowflake-native-silver-model-structure.md)
    reaching a locked answer, not on the full migration being built. This
    is the priority ticket on this map.
- **Relationship to prior maps** (read before assuming either is settled
  counterevidence or duplicate work):
  - [pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md)
    (closed) already grilled "should the silver-merge storage path change"
    (its ticket 05) and concluded "leave it" — but that measurement was
    against `ReduceIdentityRefresh`, a stage removed entirely by PR #396's
    Stage0 consolidation. Stale, not counterevidence for this map. That
    same map's ticket 12 built and deployed a real, measured CIK-sharded
    hydrate/publish mechanism for `bootstrap-batch` (76s → 3.2s per batch) —
    likely obsolete once silver lives natively in Snowflake (no more local
    monolith/shard split to reason about at all), but not yet confirmed —
    see Ticket 06.
  - [ecs-cost-sizing](../ecs-cost-sizing/map.md) (active) is where this
    migration's trigger surfaced: `load_history`'s `WindowedBootstrap`
    monolith-hydrate cost (found live, `bootstrap-next` never got
    `bootstrap-batch`'s sharding treatment) and the $22.40 month-to-date S3
    cost line (largest single AWS cost this month). Treat as evidence
    input; don't re-derive it.
- Use `/gof-refactor-reviewer` before any ticket proposing to restructure
  `silver_store.py` or `silver_protection.py` — matches
  `pipeline-throughput-architecture`'s own standing preference for this
  exact code.
- Mode: decision-spec only (wayfinder default, not overridden). Every
  ticket here decides; implementation is a separate follow-up pass.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- [Design the Snowflake-Native Silver Layer's Model Structure](issues/01-design-snowflake-native-silver-model-structure.md) — new append-only `EDGARTOOLS_SILVER_LANDING` schema (reuses SOURCE's native-pull apparatus, simplified to plain INSERT); final silver tables are uniformly `dynamic_table` (current-state, window-function collapse) rather than a per-table incremental/snapshot mix — chosen specifically because it needs zero new dbt-run trigger infrastructure, unlike `incremental` models; CIK-partitioning and the operational/lease tables' disposition are explicitly deferred to Tickets 06 and 02 respectively.
- [Decide the Concurrent-Writer Model for Snowflake-Native Silver](issues/02-decide-concurrent-writer-model.md) — there's no promotion-race conflict class left to replace at all (append-only per-row INSERT, confirmed-disjoint CIK windows); the whole ETag/promote-with-retry/candidate-canonical-merge apparatus retires outright. `sec_fetch_active`/`pipeline_run_lease` is a separate, unrelated mechanism and stays. `parse_sequence` is a row-level Snowflake `SEQUENCE`. `MaxConcurrency:1` stays for now, pending live-tested (not assumed) evidence at rollout.
- [Decide the Replacement Path for Direct Silver Consumers](issues/03-decide-direct-silver-consumer-replacement.md) — `gold_models.py`'s ~20 Python builders retire entirely in favor of dbt gold `ref()`-ing dbt silver directly, which also retires `EDGARTOOLS_SOURCE`'s current gold-mirror purpose and structurally moots the `iter_gold_tables` OOM-mitigation concern; `validate_data_quality.py`'s separate `build_gold` call becomes SQL assertions against live Snowflake gold; MDM's `ShardedSilverReader`/`_TABLES` allowlist retires in favor of Snowflake-native GRANTs on a dedicated reader role, fixing the exact silent-gap failure shape that caused the `INSTITUTIONAL_HOLDS`/`EMPLOYED_BY` incidents.
- [Decide the Ad-Hoc Reprocessing Story](issues/04-decide-ad-hoc-reprocessing-story.md) — today's "one workflow" is really five distinct mechanisms, resolving into three capability classes: SEC-fetching reprocessing (targeted-resync/full-reconcile/--force) is unaffected; bronze-only re-merge (parse-*-bronze) becomes a CLI re-parse into the append-only landing zone, simplified not downgraded; manual diagnosis (diagnose-silver-anomalies.py) keeps its read/print-remediation shape but its remediation output shifts from UPDATE/DELETE to a corrective INSERT or a re-parse pointer, since landing is append-only.
- [Confirm Relationship to `pipeline-throughput-architecture`'s Sharding Work](issues/06-confirm-relationship-to-sharding-work.md) — confirmed obsolete: the whole local-file sharding mechanism (checksums, hydrate/publish, UNION ALL reconstruction) has no analog in Snowflake. What survives as a concept, now decided: no explicit `CLUSTER BY` for now (rely on natural CIK-ordered load correlation), and the accession-join taxonomy gets an explicit `cik` column materialized in silver rather than left as a join every consumer must rediscover. Cross-reference note left on the closed `pipeline-throughput-architecture` map.
- [Draft the Cutover Script and Ownership Requirements](issues/05-draft-cutover-script-and-ownership-requirements.md) — landing/silver schemas owned by the existing `EDGARTOOLS_PROD_LOADER` (no new pipeline-object owner minted); MDM gets a brand-new, minimally-scoped `EDGARTOOLS_PROD_MDM_SILVER_READER` role with `FUTURE`-scoped grants (no allowlist to drift). Shipped as real, tested artifacts, not prose: `infra/scripts/generate_silver_landing_ddl.py` (a genuine reflection-based generator, via DuckDB introspection since `silver_store.py`'s schema isn't SQLAlchemy) plus its committed snapshot and a second bootstrap file for the future dbt-managed `EDGARTOOLS_SILVER` schema and the MDM reader role. Caught a real bug while building it: `pipeline_run_lease` doesn't belong in the append-only landing zone despite being listed in `PROTECTED_TABLE_REGISTRY`.

**Map closed — all six tickets resolved.** Destination reached: a locked
target architecture (append-only Python-populated landing zone → uniformly
`dynamic_table` dbt silver models → unchanged gold SQL just pointed at a
new connection), a concurrent-writer model with no promotion race left to
replace, every direct silver consumer's replacement path named, the
ad-hoc reprocessing story preserved across three capability classes, the
sharding relationship confirmed and cross-referenced, and the first two
real provisioning scripts committed and tested. Implementation is now a
normal follow-up pass — this map's Destination was reaching a decision
someone can implement without further architecture debate, not doing that
implementation itself.

## Not yet specified
- Snowflake compute cost (warehouse sizing/credits) for work that's
  currently ~free local DuckDB CPU — not estimable until the model
  structure and expected refresh cadence/pattern are decided.
- Exact cutover/rollback mechanics — how an in-flight `load_history`
  execution's understanding of "silver" transitions across the cutover
  boundary. Too early to specify before a target model exists to cut over
  to.

## Out of scope

<!-- none identified yet; fog resolves into tickets or here as the map advances -->
