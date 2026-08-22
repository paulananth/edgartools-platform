# 01 — Audit residual_holds_graph's mdm-large steps for the unscoped-load shape

Type: task
Status: resolved

## Question

`residual_holds_graph` (`infra/scripts/deploy-aws-application.sh`, ~line
5124) is the one confirmed-live production path that runs MDM relationship
derivation on `mdm-large` outside of `mdm run --entity-type all`. Audit
each of its 7 steps for the MANAGES_FUND-shape risk — an unscoped full
load of a shared table before the code knows what subset it needs — and
fix any genuine gap the same way MANAGES_FUND/INSTITUTIONAL_HOLDS were
fixed (batch-scope the prime, release each batch's cache,
red-before-green regression test).

Steps to check:
- `MdmSecurities` (`mdm run --entity-type security`) and `MdmPersons`
  (`mdm run --entity-type person`) — these call `MDMPipeline.run_securities`/
  `run_persons`, a *different* subsystem from relationship derivation
  (entity resolution, not `derive_relationships()`). Confirm whether the
  mdm-run-throughput map's bulk-prefetch/bounded-round-trip fix for these
  also happens to bound memory, or whether there's a separate unscoped-load
  risk here. If a gap surfaces, it may need to graduate as a new ticket
  rather than be folded into this one — use judgment once you see what's
  actually there.
- `MdmIsInsider`, `MdmHolds`, `MdmCompanyHolds` — standalone
  `mdm derive-relationships --relationship-type X` calls for IS_INSIDER,
  HOLDS, COMPANY_HOLDS. Live row counts measured 2026-08-21 (902, 395,
  3,148 respectively) are all tiny relative to MANAGES_FUND's 563,631 —
  re-verify these are still small before concluding no fix is needed; if
  any has grown materially, treat it the same as INSTITUTIONAL_HOLDS was
  (pre-emptive fix before it becomes a live incident, not after).
- `MdmInstitutionalHolds` — already fixed tonight
  (`_SELF_PRIMING_RELATIONSHIP_TYPES`, `_derive_institutional_holds_batch`,
  PR #435/#436). Confirm this step's actual invocation
  (`--target-per-type 50000`) is consistent with the batched fix and
  doesn't need any further adjustment specific to this call site.
- `mdm export` (both the mid-pipeline call and the one inside
  `wire_mdm_tail`) — a different writer entirely
  (`_build_snowflake_writer`/`_build_snowflake_mirror_writer` in
  `edgar_warehouse/mdm/export.py`/`cli.py`). Check whether it has any
  unscoped full-table read/write shape of its own — this has never been
  investigated for this specific risk.

## Blocked by

None — can start immediately.

## Answer

Audited all 7 steps against live-measured evidence (row counts re-queried
2026-08-22 against real MDM Postgres and the real canonical silver shards,
not estimates). Two genuine gaps found and fixed; the rest confirmed safe
with evidence recorded.

**`MdmIsInsider`/`MdmHolds`/`MdmCompanyHolds` — genuine gap, fixed.**
`_derive_relationship_type`'s shared dispatcher called
`sync_engine.prime_relationship_type(rel_type_name, defer_flush=True)`
**unscoped** for every type not in `_SELF_PRIMING_RELATIONSHIP_TYPES` —
IS_INSIDER, HOLDS, and COMPANY_HOLDS were all still on this path, the exact
MANAGES_FUND/INSTITUTIONAL_HOLDS OOM shape, just not yet at their scale.
Re-measuring live MDM Postgres (2026-08-22, superseding this map's
2026-08-21 baseline) showed real growth, not static small counts:
IS_INSIDER 902 → 1,552 (+72%), HOLDS 395 → 3,093 (+683%), COMPANY_HOLDS
3,148 → 33,398 (+961%, ~10.6x in ~24h) — proof that "currently small" is
not a durable safety argument for this pattern, matching the ticket's own
instruction to treat material growth like INSTITUTIONAL_HOLDS's pre-emptive
fix, not wait for an incident.

Fixed by adding all three to `_SELF_PRIMING_RELATIONSHIP_TYPES` and
restructuring `_derive_is_insider`/`_derive_holds`/`_derive_company_holds`
(`edgar_warehouse/mdm/pipeline.py`) to resolve each invocation's touched
source entities (person for IS_INSIDER/HOLDS, company for COMPANY_HOLDS)
*before* priming, then call `prime_relationship_type(..., source_entity_ids=
<that batch's resolved ids>)`, then `unprime_relationship_type` in a
`finally`. Unlike MANAGES_FUND/INSTITUTIONAL_HOLDS, no outer CRD/CIK-range
batching loop was needed — these three already read one bounded batch of
*new* source rows per invocation (via `_bounded_relationship_sql`'s
`remaining`/`existing` LIMIT), so the fix only had to scope the prime to
that one batch's touched entities, reusing already-side-effect-free
resolver calls (`_person_entity_id`, dict lookups) rather than duplicating
them. Red-before-green: 3 new tests in
`tests/mdm/test_pipeline_relationships.py`
(`TestPrimeScopingForOwnershipDerivedTypes`) each seed a pre-existing
relationship for an "out of scope" entity untouched by the run's new source
rows, spy on `prime_relationship_type`, and assert the scope excludes that
entity and equals exactly the touched set — confirmed failing
(`prime_calls[0] is None`, i.e. unscoped) before the fix, passing after.
Full `tests/mdm/test_pipeline_relationships.py`: 66 passed.

**`MdmSecurities`/`MdmPersons` (`run_securities`/`run_persons`) — confirmed
safe, different mechanism from MANAGES_FUND's.** These read via
`self.silver.fetch(sql)` (DuckDB/`ShardedSilverReader`, not a Postgres ORM
prime) with a `LEFT JOIN sec_company_filing` — that filing table is large
(7,230,709 rows live-measured across all 4 canonical shards, downloaded and
queried directly:
`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/shards/`),
but the JOIN executes inside DuckDB's vectorized engine; only the bounded
*result* set (ownership-transaction/reporting-owner rows: 14,987 non/
derivative-txn rows, 7,911 reporting-owner rows, live-measured across all 4
shards 2026-08-22) crosses into Python. No unscoped Python-side hydration
occurs — categorically different from MANAGES_FUND's ORM-object-per-row
shape.

Also closed the loop on `residual_holds_graph`'s own history: the 2026-07-25
prod OOM this map's task-profile bump (`mdm-medium 2GB → mdm-large 8GB`,
`infra/scripts/deploy-aws-application.sh`'s own comment) mitigated but never
root-caused. The code as of that incident (commit `5e04e211`) ran
`run_securities`/`run_persons` fully sequential, per-row, with a live
per-row `_company_entity_id` Postgres query and no resumable ledger — and
`SecurityResolver.resolve_one`/`run_survivorship_for_entity` is exactly the
function this session's earlier, separate stage-bloat investigation found
and fixed (`edgar_warehouse/mdm/survivorship.py`, commit `ad8443ac`,
"stop `mdm_entity_attribute_stage`'s unbounded duplicate growth"): every
`resolve_one` call on an unchanged row re-inserted a fresh stage row with no
dedup, and `run_survivorship_for_entity` read *all* of them back unbounded
per entity — live-measured that same investigation, 8,560-12,547 duplicate
stage rows for a single heavily-refiled security. That fix (already merged
to `main` before this map branched) closes the July 25 root cause as a
side effect; no further action needed here.

**`MdmInstitutionalHolds`'s `--target-per-type 50000`** — consistent with
the existing fix. `_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE` is 1000, so this
invocation runs at most ~50 CIK-range batches before hitting target, each
already scoped/released per `_derive_institutional_holds_batch`. No
call-site-specific adjustment needed.

**Both `mdm export` steps** — checked all methods `mdm export`'s CLI
handler actually calls (`export_all_pending`, `export_all_pending_relationships`,
`export_active_relationship_endpoints`, `edgar_warehouse/mdm/cli.py`). The
first two drain in bounded `LIMIT batch_size` loops (default 500) — safe,
no unscoped read. `export_active_relationship_endpoints` does run two
unscoped `SELECT DISTINCT source_entity_id`/`target_entity_id` queries
across every active relationship row with no LIMIT — structurally similar
to the audited pattern, but categorically lighter: Postgres computes the
DISTINCT server-side, so the Python-side result is bounded by *distinct
entity count* (≤226,207 today: 130,615 fund + 67,807 company + 24,447
adviser + 2,985 security + 343 person + 10 audit_firm, live-measured), not
relationship-row count, and each entry is a lightweight UUID string, not a
full ORM row. This is also inherent to the method's job (an idempotent
full-set seal, by design meant to touch every active endpoint each run) —
not a "loaded data it doesn't need yet" bug. Recording this as checked and
safe today, not a genuine gap — revisit only if total entity count grows by
orders of magnitude, which is a very different distance from today's
scale than COMPANY_HOLDS's 10x/day was.

Full `tests/mdm/` suite: 551 passed. Full repo suite: 2323 passed, 4 skipped,
35 subtests passed, only the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures documented in CLAUDE.md.
Not yet deployed — this ticket's mandate is investigate-and-fix
in the codebase; deployment is a separate, explicit follow-up per the
spec's Out-of-Scope section.
