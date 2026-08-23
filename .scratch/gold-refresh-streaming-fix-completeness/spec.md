Status: ready-for-agent

Parent: [Ticket 03 — Confirm gold-refresh's streaming fix is the complete story for the unscoped-load shape](../large-profile-unscoped-load-audit/issues/03-confirm-gold-refresh-streaming-fix-is-complete.md), a child of the [Large-profile unscoped-load audit](../large-profile-unscoped-load-audit/map.md) wayfinder map.

## Problem Statement

Tonight, a live production Step Functions execution OOM-killed on the
`MdmRun` state because `GraphSyncEngine.prime_relationship_type` loaded an
entire shared relationship table (563,631 rows, ~2GB of ORM objects) into
memory before the code knew what subset it needed. The gold-refresh path
had a related, earlier incident: `build_gold()`'s whole-dict
materialization OOM'd `daily_incremental`'s first production run mid-
`sec_thirteenf_holding`, fixed by the gold-build-memory-reliability map's
streaming rewrite (`iter_gold_tables()`, since renamed to
`iter_source_export_tables()` by the single-path-per-layer map). That fix
is confirmed live and working — CloudWatch showed `sec_thirteenf_holding`
completing cleanly on the 8192MB `large` profile after the fix.

Whether that fix is the *complete* picture for the unscoped-load shape
specifically — not just the whole-dict-materialization shape it targeted
— was unconfirmed. Investigation while writing this spec found:

- **The real production caller is genuinely streaming.**
  `warehouse_orchestrator.py`'s `SOURCE_EXPORT_COMMANDS` path (what
  `gold-refresh` actually runs in every one of its 6+ call sites) calls
  `iter_source_export_tables()` and writes each table via
  `write_source_export_table_manifest_entry()` one at a time — build,
  write to storage, export to Snowflake, discard, next. No full-dict pass
  exists anywhere in this live path.
- **One more unscoped-load instance was found**, structurally different
  from MANAGES_FUND's shape: `_build_sec_thirteenf_holding()` (and likely
  several sibling `_build_*` functions for the largest source tables)
  issues one unbounded `SELECT ... FROM sec_thirteenf_holding` via DuckDB
  and materializes the full 6.8M-row result as a single PyArrow `Table`.
  This is columnar Arrow memory, not per-row SQLAlchemy ORM objects — a
  different, generally more memory-efficient mechanism than MANAGES_FUND's
  — and it already has real empirical headroom evidence: the same
  gold-build-memory-reliability ticket 03 confirmed this exact builder
  completing cleanly (6,799,919 rows, no OOM) on the 8192MB `large`
  profile. It is not a confirmed-broken gap; it is a confirmed-present,
  structurally-different, already-once-proven-safe-at-current-volume
  pattern whose safety margin has never been formally measured.
- **`validate_data_quality.py`'s continued use of the non-streaming
  `build_source_export()`** (which materializes the whole gold layer as a
  dict, "only safe for callers that need random access across the full
  set," per its own docstring) is real, but the `validate-data-quality`
  CLI command has zero references anywhere in `infra/`/`scripts/` — it is
  not wired into any Step Functions state machine or scheduled pipeline.
  It is not a `large`-profile production risk today; it is a manual/ad-hoc
  operator command whose own memory needs have never been sized.
- **A likely-dead third caller**: `application/workflows/serving_publish.py`
  has its own `build_source_export` re-export wrapper with zero callers
  found anywhere in the codebase (production or test).

## Solution

Formally confirm each of these findings with the rigor the ticket asks
for — real measurements, not assumptions — and close out whichever of
them still need action. Specifically: measure the actual memory headroom
of the largest single-table `_build_*` builders (not just "it didn't OOM
once"), decide whether `validate_data_quality.py`'s unscoped materialization
needs any guardrail given it's operator-invoked rather than scheduled, and
confirm or clean up the apparently-dead `serving_publish.py` wrapper. Where
this confirms the existing streaming fix plus the findings above are
already the complete, acceptable picture, record that explicitly — this
ticket's whole point is that a confirmation is a valid, complete outcome
here, not a mandate to build a new fix.

## User Stories

1. As the platform operator, I want confirmation, with a citation to the
   actual current production code, that every `gold-refresh` call site
   goes through `iter_source_export_tables()`'s per-table streaming loop
   and never falls back to a full-dict pass — not just a claim that it
   "should," but a traced call graph.
2. As the platform operator, I want the largest `_build_*` builders (at
   minimum `_build_sec_thirteenf_holding`; survey the rest of
   `source_dimensional_export.py` for siblings of comparable source-table
   size) measured for real peak memory during their single unbounded
   query + Arrow-table materialization, against the current row counts of
   their source tables — not inferred from "it completed once in
   CloudWatch," which proves it didn't fail, not how much headroom exists.
3. As the platform operator, I want to know how much further those source
   tables can grow before this columnar-Arrow shape (structurally
   different from MANAGES_FUND's ORM shape, but still an unscoped full
   read) becomes a real risk on the 8192MB `large` profile, so this isn't
   revisited only after the next OOM.
4. As the platform operator, I want `validate_data_quality.py`'s
   `build_source_export(db)` usage confirmed as genuinely unscheduled (no
   Step Functions/deploy-script reference) — and if it's ever intended to
   run at production scale, a decision recorded on whether it needs the
   same streaming treatment or whether it's acceptable to leave
   memory-unbounded given it's operator-invoked.
5. As a future engineer, I want `application/workflows/serving_publish.py`'s
   `build_source_export` wrapper confirmed dead (zero callers) or, if it
   turns out to have a caller this investigation missed, that caller
   identified and checked against the same shape.
6. As a future engineer, I want a clear written distinction between "the
   gold-build-memory-reliability fix already fully covers this" and "this
   is a new, related-but-distinct finding this ticket surfaced" so the
   two pieces of work aren't confused with each other later.
7. As a future engineer, I want any fix built here (if the memory
   measurement in story 2/3 reveals a real, not just theoretical, risk) to
   follow the same pattern MANAGES_FUND/INSTITUTIONAL_HOLDS were fixed
   with — batch by a natural key (most likely CIK range, matching
   INSTITUTIONAL_HOLDS's precedent, since `sec_thirteenf_holding` is
   CIK-keyed), with a red-before-green regression test — adapted for
   DuckDB/Arrow's columnar read shape rather than SQLAlchemy ORM.
8. As the on-call operator, I want to know whether this ticket's overall
   answer is "confirmed complete, no action needed" or "here is the
   specific residual risk and its measured safety margin," so I have a
   concrete number to watch rather than a vague sense that gold-refresh
   might still be risky.

## Implementation Decisions

- **One seam** (confirmed with the user before writing this spec):
  `iter_source_export_tables(db)`
  (`edgar_warehouse/serving/source_dimensional_export.py`) — the existing
  generator all builders run through, already characterized by
  `tests/unit/test_source_dimensional_export_streaming.py` (schema/
  table-name parity between the dict and generator forms, plus laziness —
  a later builder is provably not invoked until the generator reaches it).
  Any new test needed for a finding in this ticket goes through this same
  seam.
- **Memory measurement method**: mirror tonight's MANAGES_FUND/
  INSTITUTIONAL_HOLDS investigation — `psutil.Process().memory_info().rss`
  around the specific builder call(s) against a real or realistically-sized
  local copy of canonical `silver.duckdb`, not `resource.getrusage()`
  (sticky high-water-mark, unit-inconsistent across platforms — this
  session's own MANAGES_FUND investigation made and caught this exact
  mistake once already).
- **If a real risk is confirmed** for `_build_sec_thirteenf_holding` (or a
  sibling builder), the fix is CIK-range batching inside that one builder
  — read and yield Arrow record batches per CIK range instead of one
  unbounded `SELECT`, concatenating or writing incrementally rather than
  materializing the whole table before returning. This changes one
  builder's internals, not `iter_source_export_tables()`'s own
  outer-loop contract (still one `(table_name, table)` pair per table from
  the caller's perspective) — unless the measurement shows even one
  fully-materialized table's Arrow representation is itself too large for
  8192MB, in which case the outer streaming contract may need to change
  too (yielding partial tables) — that's a design decision this ticket's
  own measurement should drive, not presume.
- **`validate_data_quality.py`**: since it's confirmed unscheduled today,
  no code change is required by default. Record the finding and make an
  explicit, deliberate call: either (a) leave it as-is with a note that it
  is an operator-invoked, not scheduled, risk, or (b) if there's reason to
  believe it will be scheduled/automated soon, flag that as fog for the
  parent map rather than build a fix speculatively here.
- **`serving_publish.py`'s dead wrapper**: confirm via a repo-wide search
  (not just this session's grep) that it truly has zero callers before
  concluding it's dead. If confirmed dead, note it for cleanup — deletion
  itself can be this ticket's own small fix (it's a one-file, zero-caller
  removal, low risk) or deferred to a separate cleanup ticket, whichever
  the implementing agent judges appropriate given how much of this
  ticket's budget the memory-measurement work (stories 2/3) consumes.
- **No changes to `gold-refresh`'s Step Functions definition, task
  profile, or retry/timeout configuration** are in scope — this ticket is
  about the Python-level load shape inside the builders, not the
  orchestration around them.

## Testing Decisions

- If the memory measurement confirms a real risk and a batching fix is
  built, follow the same red-before-green discipline as tonight's two
  fixes: a test proving the *old* shape reads the whole table in one
  unbounded call (or, more practically, a memory/row-count assertion that
  fails without the fix), then green after batching is added.
  `tests/unit/test_source_dimensional_export_streaming.py`'s existing
  laziness-assertion style (a later builder not invoked until reached) is
  the closest prior art for asserting a builder's *internal* batching is
  real, not just its outer generator position.
- If no code fix is needed (the measurement confirms adequate headroom),
  no new test is required — but the measured numbers (peak memory, row
  count, headroom margin, current source-table growth rate if knowable)
  must be recorded in the ticket's resolution as the evidence, not just an
  assertion that it's "probably fine."
- Full `tests/unit/` suite (all four `test_source_dimensional_export_*.py`
  files) plus the full repo suite must stay green — matching tonight's
  baseline (2320 passed, 4 skipped, only the 2 pre-existing unrelated
  `test_bootstrap_dbt_snowflake_secret.py` failures documented in
  CLAUDE.md).

## Out of Scope

- The other 3 tickets on the Large-profile unscoped-load audit map
  (`residual_holds_graph`'s mdm-large steps, the core warehouse commands'
  audit, `load_history`'s internal `large`-profile states) — each is its
  own separate spec/session.
- Re-fixing the whole-dict-materialization shape gold-build-memory-
  reliability already closed — this spec only adds a check for the
  narrower, single-builder unscoped-read shape on top of that already-
  confirmed-working fix.
- Any change to `gold-refresh`'s Step Functions definition, scheduling,
  or task-profile sizing.
- Building automation or scheduling for `validate-data-quality` — it stays
  a manual/ad-hoc command unless this ticket's investigation finds a
  concrete reason that's about to change.
- Deploying or restarting any production pipeline as a result of this
  work — build any fix and its tests; deployment is a separate, explicit
  follow-up decision.

## Further Notes

- This ticket's "confirmation" framing matters: unlike tickets 01/02 which
  are actively hunting for a live gap, ticket 03 starts from a fix that's
  already confirmed working in production. The bar for action here is
  "does the *measured* safety margin justify a fix now," not "does an
  unscoped read exist at all" — an unscoped read that's provably safe for
  years at current growth rates is a different answer than one that's
  close to its ceiling.
- Per the parent map's Notes: if this investigation surfaces a genuinely
  new, differently-shaped risk elsewhere in the gold-export path that this
  spec doesn't name, graduate it as a new ticket on the map rather than
  fold it in here, per wayfinder's fog-of-war convention.
