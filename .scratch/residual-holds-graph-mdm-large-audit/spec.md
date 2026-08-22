Status: ready-for-agent

Parent: [Ticket 01 — Audit residual_holds_graph's mdm-large steps](../large-profile-unscoped-load-audit/issues/01-audit-residual-holds-graph-mdm-large-steps.md), a child of the [Large-profile unscoped-load audit](../large-profile-unscoped-load-audit/map.md) wayfinder map.

## Problem Statement

Tonight, the `MdmRun` state of a live production Step Functions execution
(`edgartools-prod-bronze-seed-silver-gold`) OOM-killed repeatedly. The root
cause: `GraphSyncEngine.prime_relationship_type("MANAGES_FUND")`
unconditionally loaded every active MANAGES_FUND relationship row (563,631
rows, ~2GB of ORM objects) into memory before the code knew which
advisers the run actually needed — a structural shape, not a data-volume
problem. It was fixed by batching the load by adviser CRD, priming only
each batch's own advisers, and releasing that batch's cache before the
next. The same shape was then found and pre-emptively fixed in
INSTITUTIONAL_HOLDS (0 rows today, but its 6.8M-row source table makes it
the next type most likely to reproduce the incident).

`residual_holds_graph` is a separate, already-live production Step
Functions state machine that runs 7 steps on the `mdm-large` (8GB) Fargate
profile: `MdmSecurities`, `MdmPersons`, `MdmIsInsider`, `MdmHolds`,
`MdmCompanyHolds`, `MdmInstitutionalHolds`, and `mdm export` (twice — once
mid-pipeline, once inside the shared `wire_mdm_tail` helper). It is the one
confirmed-live path that invokes `INSTITUTIONAL_HOLDS` derivation directly,
independent of `mdm run --entity-type all` — real evidence that tonight's
fix protects a path that actually runs in production, not just a
theoretical one. None of its other 6 steps have been checked for the same
unscoped-full-load shape. Nobody wants to find the next occurrence of this
bug live, mid-incident, the way the first two were found.

## Solution

Audit each of `residual_holds_graph`'s 7 steps against the MANAGES_FUND
shape — an unscoped load of a shared table/dataset before the code knows
which subset the current run needs — using real, measured evidence from
live production data (row counts, table sizes, concentration), not
estimates. Where a genuine gap is found, fix it the same way MANAGES_FUND
and INSTITUTIONAL_HOLDS were fixed: batch-scope the load along whatever key
the domain naturally groups by, release each batch's state before the
next, and add a red-before-green regression test that proves the scoping
is real (not just that the code runs). Where no gap is found, that is
itself a valid, recorded outcome — this is an audit, not a mandate to
change every file it touches.

## User Stories

1. As the MDM platform operator, I want `MdmSecurities`'s
   `run_securities()` call checked for an unscoped full read of ownership
   transaction rows, so that a future spike in ownership-filing volume
   cannot reproduce the MANAGES_FUND OOM on this step.
2. As the MDM platform operator, I want `MdmPersons`'s `run_persons()`
   call checked the same way, for the same reason on the person-resolution
   side.
3. As the MDM platform operator, I want confirmation of whether the
   mdm-run-throughput map's bulk-prefetch/bounded-round-trip fix for
   `run_securities`/`run_persons` (built to solve a *speed* problem)
   incidentally also bounds memory, so I know whether that prior work
   already covers this risk or whether it's an independent gap.
4. As the MDM platform operator, I want `MdmIsInsider`'s
   `derive-relationships --relationship-type IS_INSIDER` call re-verified
   against live row counts (902 as of 2026-08-21), so a stale "it's small"
   assumption doesn't silently go unwatched as the type grows.
5. As the MDM platform operator, I want `MdmHolds`'s HOLDS derivation
   (395 rows as of 2026-08-21) re-verified the same way.
6. As the MDM platform operator, I want `MdmCompanyHolds`'s COMPANY_HOLDS
   derivation (3,148 rows as of 2026-08-21) re-verified the same way,
   since it's the largest of the three currently-small types and the
   closest to warranting a pre-emptive fix if it has grown.
7. As the MDM platform operator, I want confirmation that
   `MdmInstitutionalHolds`'s specific invocation
   (`--target-per-type 50000`) is consistent with tonight's
   `_derive_institutional_holds_batch` fix and needs no further
   call-site-specific adjustment.
8. As the MDM platform operator, I want both `mdm export` steps (the
   mid-pipeline `_build_snowflake_writer`/`_build_snowflake_mirror_writer`
   call and the one inside `wire_mdm_tail`) checked for any unscoped
   full-table read/write shape, since this writer path has never been
   audited for this specific risk.
9. As a future engineer debugging a `residual_holds_graph` OOM, I want a
   written record of what was checked and what was found for each of the
   7 steps, so I don't have to re-derive this investigation from scratch.
10. As a future engineer, I want any new fix built here to follow the
    exact pattern already proven twice tonight (batch by natural key,
    scoped `prime_relationship_type(..., source_entity_ids=...)`,
    `unprime_relationship_type` in a `finally`, red-before-green test), so
    the codebase doesn't accumulate three slightly different variants of
    the same fix.
11. As a future engineer, I want any genuinely new risk found outside this
    ticket's 7 steps (e.g. inside `run_securities`/`run_persons`'s own
    resolver internals, if the audit finds one) to graduate into its own
    ticket on the parent map rather than be silently folded in here, per
    the map's own fog-of-war convention.
12. As the on-call operator, I want to know, for each of the 7 steps,
    whether it currently has *any* real OOM risk at today's data volumes,
    so I can prioritize watching the riskiest ones (if any) between now
    and this ticket's next revisit.

## Implementation Decisions

- **Three seams, one per subsystem** (confirmed with the user before
  writing this spec — no single umbrella seam honestly covers all three,
  since the only thing above them is the CLI argument parser):
  - **Entity resolution** (`MdmSecurities`, `MdmPersons`):
    `MDMPipeline.run_securities()` / `MDMPipeline.run_persons()`.
  - **Relationship derivation** (`MdmIsInsider`, `MdmHolds`,
    `MdmCompanyHolds`, `MdmInstitutionalHolds`):
    `MDMPipeline.derive_relationships(relationship_types=[...])`, using the
    `GraphSyncEngine.prime_relationship_type`/`unprime_relationship_type`
    spy pattern already established for MANAGES_FUND/INSTITUTIONAL_HOLDS.
  - **Export** (both `mdm export` steps): `MDMExporter.export_pending()` /
    `export_all_pending()` / `export_pending_relationships()` /
    `export_all_pending_relationships()`.
- **`run_securities`/`run_persons` audit scope**: both currently read via
  `self.silver.fetch(sql)` with no bound unless an explicit `--limit` is
  passed (the `residual_holds_graph` call sites pass none). This is a
  silver/DuckDB read, not a Postgres ORM hydration — a different mechanism
  from MANAGES_FUND's shape, but the *consequence* (loading more than the
  current run needs, all at once) is the same family of risk. Measure
  real row counts for the underlying silver queries
  (`sec_ownership_non_derivative_txn`/`sec_ownership_derivative_txn` for
  securities; the equivalent ownership-reporting-owner query for persons)
  against the current canonical `silver.duckdb`, not the ~15K figure cited
  in `run_securities`'s own docstring from an earlier investigation — that
  number may be stale.
- **Relationship-derivation types**: re-run the same
  `SELECT rel_type_name, COUNT(*) ... GROUP BY rel_type_name` query against
  live MDM Postgres used to establish tonight's baseline (IS_INSIDER 902,
  HOLDS 395, COMPANY_HOLDS 3,148, MANAGES_FUND 563,631,
  INSTITUTIONAL_HOLDS 0) — do not assume these numbers are still current;
  re-measure before concluding any type is still safely small.
- **Fix pattern, if a gap is found**: mirror
  `_derive_manages_fund`/`_derive_manages_fund_batch` and
  `_derive_institutional_holds`/`_derive_institutional_holds_batch`
  exactly — batch by the domain's natural key (adviser CRD for
  MANAGES_FUND, CIK range for INSTITUTIONAL_HOLDS; whatever the audited
  type's natural key is), add the type to
  `_SELF_PRIMING_RELATIONSHIP_TYPES` if it's a relationship-derivation
  type, scope `prime_relationship_type(..., source_entity_ids=...)` per
  batch, and release with `unprime_relationship_type` in a `finally`
  block so a batch's cache never survives an early exit.
- **No changes to `residual_holds_graph`'s Step Functions definition
  itself** (task profile, step ordering, retry config) are in scope here
  — this ticket is about the Python-level load shape inside each step's
  command, not the orchestration around it.
- **A clean bill of health is a valid outcome.** If a step's audit finds
  no gap, record the evidence checked (row counts, table sizes, the
  reasoning for why the current shape is safe) rather than treating "no
  fix needed" as an incomplete result.

## Testing Decisions

- Tests should assert on the **scoping being real**, not just that the
  code runs without error — the pattern that made tonight's
  `test_manages_fund_processes_advisers_in_bounded_crd_batches` and
  `test_institutional_holds_primes_scoped_to_each_cik_batchs_advisers`
  tests meaningful: spy on `GraphSyncEngine.prime_relationship_type`,
  assert multiple disjoint, non-overlapping, non-empty `source_entity_ids`
  sets across batches, and assert the union covers every affected entity.
- Any new regression test for a relationship-derivation gap must be
  proven **red without the fix** before it's accepted as green with the
  fix — confirmed via `git stash`/reverting the fix locally and re-running,
  matching the discipline both prior fixes tonight followed.
- Prior art, by subsystem:
  - Relationship derivation:
    `tests/mdm/test_pipeline_relationships.py`'s
    `test_manages_fund_processes_advisers_in_bounded_crd_batches` and
    `test_institutional_holds_primes_scoped_to_each_cik_batchs_advisers`;
    `tests/mdm/test_graph.py`'s `TestPrimeRelationshipTypeScoping`.
  - Entity resolution: `tests/mdm/test_run_securities_persons_concurrency.py`.
  - Export: `tests/mdm/test_export.py`.
- If a step's audit concludes no fix is needed, no new test is required —
  but the evidence (real row/table-size numbers) must be recorded in the
  ticket's resolution, not just asserted informally.
- Full `tests/mdm/` suite and full repo suite must stay green (matching
  tonight's baseline: 543 and 2320 passed respectively, only the 2
  pre-existing unrelated `test_bootstrap_dbt_snowflake_secret.py` failures
  documented in CLAUDE.md).

## Out of Scope

- The other 3 tickets on the Large-profile unscoped-load audit map
  (core warehouse `large`-profile commands, gold-refresh's streaming-fix
  completeness, `load_history`'s internal `large`-profile states) — each
  is its own separate spec/session.
- Any change to `residual_holds_graph`'s Step Functions definition,
  retry/timeout configuration, or task profile sizing.
- MDM entity-resolution subsystems not reachable from
  `residual_holds_graph` (`run_companies`, `run_advisers`, `run_funds`) —
  out of scope for *this* ticket; a broader entity-resolution audit, if
  warranted, belongs on the parent map's fog-of-war list.
- Deploying or restarting any production pipeline as a result of this
  work — build the fix (if needed) and its tests; deployment is a
  separate, explicit follow-up decision.

## Further Notes

- This ticket's audit doubles as validation of tonight's
  INSTITUTIONAL_HOLDS fix in its one confirmed-live production call site
  (`MdmInstitutionalHolds`) — worth explicitly noting in the resolution
  whether this step's specific `--target-per-type 50000` invocation was
  exercised as part of the audit, not just the generic
  `mdm run --entity-type all` path both fixes were originally verified
  against.
- Per the parent map's Notes: if the entity-resolution audit
  (`run_securities`/`run_persons`) surfaces a genuine gap inside the
  resolver internals themselves (rather than in the bulk-read shape this
  spec scopes), don't fold it into this ticket — graduate it as a new
  ticket on the map, per wayfinder's fog-of-war convention.
