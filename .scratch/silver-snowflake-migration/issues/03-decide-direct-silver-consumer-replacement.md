# Decide the Replacement Path for Direct Silver Consumers

Type: grilling
Status: resolved
Blocked by: 01

## Question

`edgar_warehouse/serving/gold_models.py`'s ~20+ `_build_*` functions
(`_build_dim_company` etc.) and MDM's `ShardedSilverReader` both query an
embedded DuckDB connection directly via raw SQL today. Once silver lives
natively in Snowflake, what replaces them?

The sharpest candidate: gold already runs entirely as dbt models on top of
Snowflake `SOURCE` — if silver also becomes dbt models (Ticket 01), does
`gold_models.py`'s Python-side table-building logic retire entirely in
favor of pure dbt gold models reading the new dbt silver models directly,
unifying the whole `SOURCE → SILVER → GOLD` chain in one engine? Or does a
real reason remain for `gold_models.py` to exist as a separate Python layer
(e.g. `iter_gold_tables`'s streaming-generator memory-pressure fix from the
gold-build-memory-reliability workstream — confirm whether that concern
still applies once gold tables are dbt-materialized directly from
Snowflake rather than built in Python and streamed to storage one at a
time)? Answer for MDM's `ShardedSilverReader` separately — its
`_TABLES` allowlist has already caused two real production gaps
(`sec_thirteenf_filing`, `sec_employment_event`, see CLAUDE.md's
"INSTITUTIONAL_HOLDS / EMPLOYED_BY" incident) from being an easy-to-forget
manual list; whatever replaces it should not reintroduce that failure
shape.

## Answer

**`gold_models.py` retires entirely.** dbt gold models get `ref()` edges
directly into the new dbt silver layer from Ticket 01 — the sharpest
candidate the ticket itself named, confirmed correct by what the
investigation found `EDGARTOOLS_SOURCE` is actually doing today: it's a
**mixed** mirror, holding both Python-built dimensional gold tables
(`COMPANY`, table comment "mirrored from the canonical warehouse gold
export") *and* near-identity silver passthroughs (`SEC_FINANCIAL_FACT`,
`SEC_THIRTEENF_HOLDING`, comment "Passthrough from silver
sec_financial_fact") — both built by the same ~20 `gold_models.py`
`_build_*` functions, both round-tripped through S3/Parquet/Snowpipe to
land in the same Snowflake account they were queried out of. Once silver
already lives natively in that account (Ticket 01), that whole roundtrip
is pure overhead: dbt gold models express the identical joins/
aggregations as SQL against `ref("silver_...")` instead of Python against
a DuckDB connection, and `EDGARTOOLS_SOURCE`'s gold-mirror purpose — the
native-pull apparatus, `LOAD_EXPORTS_FOR_RUN`'s per-table merge-key map,
`REFRESH_AFTER_LOAD`'s allowlist entries for these tables — becomes
unnecessary for anything gold-related. (`EDGARTOOLS_SOURCE`'s *other*
declared dbt source, `mdm_export`, is untouched — a separate write path
from MDM's own Postgres store, unaffected by this decision.) Unifies
`SOURCE → SILVER → GOLD` into dbt/Snowflake as one engine, matching the
map's own direction from Ticket 01.

**Direct structural consequence, confirmed not just hoped-for:** the
`iter_gold_tables()` streaming-generator fix
(gold-build-memory-reliability workstream, built specifically to stop a
Python ECS task from holding ~24 gold tables simultaneously in memory
while streaming Parquet exports one at a time) becomes **moot, not
merely improved** — there's no longer a Python process materializing
these tables in local memory at all once gold is dbt-native; Snowflake's
own engine manages each dynamic table's refresh independently. This
retires that entire OOM-mitigation concern as a side effect, not a goal
this ticket had to separately pursue.

**Second consumer, correctly separated:** `validate_data_quality.py`'s
`build_gold(db)` call is unrelated to the `warehouse_orchestrator.py`
gold-build path and needs its own replacement — **rewritten as SQL
assertions against the live Snowflake gold dynamic tables** (dbt tests or
standalone checks), reusing this project's existing `dbt test` framework
(`gold.yml` already has test coverage today) rather than inventing new
validation infrastructure or leaving a stale-data Python/DuckDB validator
running against exported, not live, state.

**MDM's `ShardedSilverReader` retires along with its `_TABLES`
allowlist.** Structural fix, not a patched failure mode: the allowlist
conflated two different jobs — "which tables exist" (a mechanical need
under DuckDB's `ATTACH`, since nothing else could discover table
existence) and "which tables MDM may read" (an implicit access boundary).
Snowflake needs neither declared: `INFORMATION_SCHEMA` is authoritative
for the first, and a dedicated MDM reader role's native `GRANT SELECT`
handles the second — properly, as an enforced boundary rather than a
silently-stale Python list. MDM queries `EDGARTOOLS_SILVER` tables
directly; an unauthorized or nonexistent table now raises a real
permission/compile error instead of silently resolving to "relationship
type has zero rows," which is exactly the failure shape that produced
both the `sec_thirteenf_filing` and `sec_employment_event` incidents.

**Deferred, not this ticket's job:** the actual dbt SQL for ~20 ported
gold models, the DDL for the new MDM reader role and its grant scope, and
when `EDGARTOOLS_SOURCE`'s now-unnecessary gold-mirror plumbing gets
physically decommissioned vs. kept briefly as a rollback path — all
implementation/rollout work for [Draft Cutover Script and Ownership
Requirements](05-draft-cutover-script-and-ownership-requirements.md).
