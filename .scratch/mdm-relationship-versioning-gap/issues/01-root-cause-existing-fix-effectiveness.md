Type: research
Status: resolved

## Question

`mdm-relationship-incremental-filters` Ticket 04 (PR #568, merged 2026-09-07,
already deployed in today's freshly-built MDM image) added
`close_relationship_version`-based deactivation for `HOLDS`/`COMPANY_HOLDS`
(zero-shares close) and `INSTITUTIONAL_HOLDS` (cross-period diff-and-close),
specifically to stop the "same source reports an updated value for an
already-open relationship version" false-conflict quarantine. Given today's
live prod data still shows large quarantine rates for exactly these three
types, is the fix genuinely not working, working-but-incomplete, or is the
observed quarantining actually harmless (duplicate reprocessing of
already-correctly-closed evidence, not real data loss)?

## Context

Live measurement, 2026-09-08, querying `mdm_relationship_instance` directly
in prod MDM Postgres (`edgartools-prod/mdm/postgres_dsn`):

**Overall quarantine rate by type (all rows, any age):**

| Type | Total | Quarantined | Rate |
|---|---|---|---|
| COMPANY_HOLDS | 165,066 | 155,327 | 94.1% |
| HOLDS | 24,295 | 21,813 | 89.8% |
| INSTITUTIONAL_HOLDS | 10,000 | 6,455 | 64.6% |
| EMPLOYED_BY | 26,250 | 13,565 | 51.7% |
| IS_INSIDER | 13,155 | 2,092 | 15.9% |
| ISSUED_BY / MANAGES_FUND | -- | 0 | 0% (structurally immune, see map's Out of scope) |

Every quarantined row (199,252 total) shares the identical
`quarantine_reason` prefix: `"conflicting overlapping evidence with no
configured mdm_relationship_source_priority winner between ..."` --
confirmed via a `GROUP BY quarantine_reason` sweep, one reason accounts for
all of them.

**Split by `created_at` before/after PR #568 landed (2026-09-07 21:21 UTC):**

| Type | Created after fix? | Total | Quarantined | Rate |
|---|---|---|---|---|
| INSTITUTIONAL_HOLDS | before | 100 | 3 | 3.0% |
| INSTITUTIONAL_HOLDS | **after** | 9,900 | 6,452 | **65.2%** |
| IS_INSIDER | before | 12,629 | 1,566 | 12.4% |
| IS_INSIDER | **after** | 526 | 526 | **100%** |
| EMPLOYED_BY | before | 19,331 | 6,798 | 35.2% |
| EMPLOYED_BY | **after** | 6,919 | 6,767 | **97.8%** |
| COMPANY_HOLDS / HOLDS | -- | -- | -- | no fresh writes since the fix to test against |

The `INSTITUTIONAL_HOLDS` "after" bucket is this session's own scoped
verification test (`institutional-holds-verify-1788865245`,
`--relationship-type INSTITUTIONAL_HOLDS --target-per-type 10000`, run
directly against the just-deployed fixed image) -- i.e. real, fresh evidence
against the current code, not stale data. `IS_INSIDER`'s 526 "after" rows
and `EMPLOYED_BY`'s 6,919 are from whatever wrote them in the ordinary
course of the freshly-restarted `daily_incremental` execution today (not
yet identified which exact run/step).

**One concrete traced example (INSTITUTIONAL_HOLDS, pair
`a7d1c5be-8feb-.../93bf2f9f-dd85-...`)** -- all 5 `mdm_relationship_instance`
versions for this (adviser, security) pair, oldest to newest by
`created_at`:

1. `quarter_end=2025-06-30`, `valid_from=2025-06-30`, `valid_to=2026-03-31`
   (**closed**), `quarantined=False` -- created 2026-09-02 (an earlier run,
   already reflects PR #568's cross-period close logic correctly: this
   version was properly closed when the manager's later quarters arrived).
2. `quarter_end=2025-09-30`, `valid_from=2025-09-30`, `valid_to=None`
   (open), `quarantined=False` -- created today 11:01:32 UTC.
3. `quarter_end=2025-12-31`, `valid_from=2025-12-31`, `valid_to=None`
   (open), `quarantined=False` -- created today 11:01:32 UTC.
4. `quarter_end=2026-03-31` (the true latest), `valid_from=2026-03-31`,
   `valid_to=None` (open, correctly), `quarantined=False` -- created today
   11:01:32 UTC.
5. `quarter_end=2025-06-30` (**same quarter and same `source_accession`
   as version 1**, byte-identical `properties`), `valid_from=2025-06-30`,
   `valid_to=None` (open), **`quarantined=True`** -- created today
   11:01:32 UTC, same batch as 2-4.

Working hypothesis from this one trace: today's scoped test re-derived an
accession (`0001104659-25-072132`, the 2025-06-30 quarter) that an earlier
run had *already* fully processed and correctly closed (version 1). The
re-insert attempt (version 5) doesn't exact-match version 1 (its default
`valid_to=None` differs from version 1's closed `valid_to=2026-03-31`, so
the "identical evidence" short-circuit in `ensure_relationship` doesn't
fire) -- so it falls through to conflict detection against `current`
(every non-quarantined, non-superseded, `is_active` row sharing this pair's
*single* `relationship_id`, which is NOT period-scoped -- all 5 versions
here share one `relationship_id` since it's derived only from
`(rel_type_id, source_entity_id, target_entity_id)`). `_intervals_overlap`
computes true against version 2 (2025-09-30, also `valid_to=None`) purely
because *both* are open-ended in the interval sense, even though
"2025-06-30 quarter" and "2025-09-30 quarter" don't semantically overlap in
real-world time. Properties differ (different quarter's shares/market
value) -> conflict -> same `source_system` ('thirteenf_filing' both sides)
-> `_resolve_source_priority` returns `"none"` -> new row quarantined.

**If this hypothesis holds, version 5 in this example is a harmless
duplicate** (the correct closed record for 2025-06-30 already exists as
version 1) -- but it does NOT explain why the scoped test re-derived an
already-fully-processed accession in the first place (wasted work, and the
mechanism generating this "harmless" quarantine noise at 65% of all rows
written is not free -- 6,452 wasted round trips in this one run alone), nor
whether this same shape also explains `IS_INSIDER`'s 100%-quarantined and
`EMPLOYED_BY`'s 97.8%-quarantined "after fix" numbers, which have **no**
deactivation/closing logic at all (PR #568 never touched those two types) --
for those, a genuine property change on an already-open pair (e.g. a role
or title update, or an updated compensation figure) has no closed
predecessor to exact-match against at all, so every such row is a real,
first-class conflict by design of the current code, not a redundant-rescan
artifact.

## Answer

**Root cause found, confirmed via source read + live checkpoint state
(not just the earlier trace/hypothesis) — this is a real, separate,
deeper bug than "the closing logic doesn't work." The closing logic
(PR #568) works correctly. The problem is that it almost never gets the
chance to run against genuinely fresh data, because the watermark that
gates it can never catch up.**

**Mechanism:** `_derive_institutional_holds` (`pipeline.py:4027`) always
restarts CIK-range iteration from the table's absolute `min_cik`
(`bounds_sql`, line 4137) on every single invocation — there is no
persisted "resume from where the last run left off" cursor into CIK
space. Every run is invoked with a bounded `--target-per-type` (10,000 in
this session's own scoped test; **50,000 in the standard production
`generation-build` pipeline itself**, confirmed via
`grep -n "target-per-type" infra/scripts/deploy-aws-application.sh`),
because `sec_thirteenf_holding` (6.8M rows) is too large to process
unbounded in one run (that 50,000 cap is defined in the operator-driven
`edgartools-prod-residual-holds-graph` state machine, not a one-off —
`infra/scripts/deploy-aws-application.sh:5753`). `_advance_relationship_watermark`'s own docstring
confirms this is deliberate: it only advances to the max `ingested_at`
among rows *actually iterated* this call, never further — correct in
isolation (so a capped run never skips rows it didn't get to), but
combined with always-restart-from-`min_cik`, the consequence is: **if
the backlog of new/changed rows accumulates faster than one capped run's
budget can consume starting from `min_cik`, the watermark can only ever
creep forward through whatever slice of CIK space the first N batches
before the cap happen to cover — it can never reach CIK ranges further
out, no matter how many runs execute.** Confirmed live: the
`mdm_relationship_derivation_checkpoint` row for `INSTITUTIONAL_HOLDS`
shows `watermark_value = '2026-07-22T03:13:43...'` — **over 6 weeks
stale** — even though `updated_at` shows today (2026-09-08 11:35:50 UTC),
i.e. runs keep executing and keep "updating" the checkpoint, but the
watermark value itself has barely moved in that time.

This exactly explains the traced example: the redundant re-derivation
of an already-closed 2025-06-30 accession wasn't a one-off — it's the
*expected* behavior of this design whenever a manager sitting early in
CIK-ascending order has *any* newly-ingested-since-`2026-07-22` row (even
one), since the whole CIK range gets re-fetched and re-walked from
scratch every run. The correctly-working PR #568 closing logic then
does its job (closes what needs closing, quarantines genuine same-source
duplicate re-inserts) — but it's being asked to redo the same early
slice of work repeatedly while the true backlog (including whatever's
sitting beyond wherever each run's cap cuts off) is never reached at all.

**Confirmed NOT unique to `INSTITUTIONAL_HOLDS`:** `_derive_manages_fund`
(`pipeline.py:2193`) has the structurally identical shape —
`sorted_crds = sorted(adviser_ids_by_crd.keys())` (line 2292) rebuilt and
restarted from the beginning on every call, same `remaining`/
`target_per_type` capping, same watermark-advance-only-what-was-iterated
contract. It shows 0% quarantine only because it passes no `properties`
to `ensure_relationship` (nothing to conflict over — same reason
`ISSUED_BY` is immune, per this map's Out of scope) — but the same
"can never advance past the first slice of CRD space if backlog exceeds
per-run capacity" throughput/coverage problem applies silently: newly-
eligible adviser-fund pairs whose CRD falls beyond a capped run's reach
may never get derived at all, indefinitely, with no error or quarantine
signal to reveal it.

**IS_INSIDER/EMPLOYED_BY's high post-fix quarantine rates are a
genuinely separate, simpler root cause** (confirmed already, no batching
involved at all for either — single unbounded fetch per type): they have
*zero* deactivation/closing logic of any kind (unaffected by PR #568,
which only touched `HOLDS`/`COMPANY_HOLDS`/`INSTITUTIONAL_HOLDS`), so
*every* genuine property change on an already-known pair is a same-source
conflict by construction, regardless of watermark health. That diagnosis
from this map's original charting stands unchanged — Tickets 02/03 remain
the right scope for those two types.

**What this changes for the rest of this map:** `INSTITUTIONAL_HOLDS`
needs a real fix here too, not just verification — a persisted,
resumable CIK-range cursor (independent of, or combined with, the
`ingested_at` watermark) so successive capped runs actually advance
through CIK space instead of restarting from `min_cik` every time.
`MANAGES_FUND` needs the identical fix for CRD space, even though it has
no visible quarantine symptom, since the underlying coverage gap is real.
This ticket's scope has grown to include designing and implementing that
cursor mechanism, in addition to the CIK/CRD-batched deactivation logic
already confirmed correct.

## Implementation

Built a persisted, resumable CIK/CRD-range cursor, decoupled from the
stable `watermark_value` the batch loops filter against, so a capped run
resumes where the last one left off instead of always restarting from
`min_cik`/CRD-index-0.

**Schema** (`edgar_warehouse/mdm/migrations/022_relationship_derivation_checkpoint_cursor.sql`,
registered in `migrations/runtime.py`): `mdm_relationship_derivation_checkpoint`
gains two new nullable `TEXT` columns -- `cursor_value` (resume position;
NULL means no sweep in progress) and `pending_watermark_value` (the
running max watermark accumulated across an in-progress sweep, since a
sweep may span many separate process runs). `watermark_value`'s NOT NULL
constraint is relaxed (a checkpoint row can now legitimately exist,
holding only cursor progress, before any sweep has ever fully completed)
-- every other relationship type's checkpoint writes are unaffected,
since they never populate a NULL `watermark_value`.

**Correctness invariant** (the thing the earlier, pre-compaction
`/gof-refactor-reviewer` consult flagged in a naive rotating-cursor
design, and this session's follow-up consult specifically re-verified):
`watermark_value` is *only* ever advanced once a sweep has visited the
*entire* CIK/CRD range under one *stable* watermark boundary --
`record_relationship_sweep_progress` (an in-progress sweep) never touches
`watermark_value` at all; only `complete_relationship_sweep` does, and
only after the loop's own `last_cik_hi_processed >= max_cik` (or the CRD
equivalent) confirms full coverage. This is what prevents the original
bug: a not-yet-revisited slice of CIK/CRD space getting silently
watermarked-out by an already-advanced watermark from unrelated,
already-visited activity in a later call.

**Pipeline integration** (`edgar_warehouse/mdm/pipeline.py`,
`_derive_institutional_holds`/`_derive_manages_fund`, mirrored
identically): reads `get_relationship_checkpoint_state` once per call,
resumes the batch loop at the persisted cursor (clamped for CIK; bisected
into the freshly-recomputed CRD list for MANAGES_FUND) instead of the
beginning, seeds the watermark accumulator with `pending_watermark_value`
instead of always starting at `None`, and after the loop either
`_complete_relationship_sweep`s (advances watermark, clears cursor) or
`_record_relationship_sweep_progress`s (persists the new resume point,
leaves watermark untouched) depending on whether the range was fully
covered. A `reconciliation_pass` never reads or writes this cursor state
at all -- it always scans the full range from the beginning and leaves
whatever ordinary-pass sweep is in progress untouched, mirroring
`_relationship_watermark`'s own existing reconciliation special-case.

**New finding, deliberately not fixed here** (surfaced by the
`/gof-refactor-reviewer` consult, filed as a follow-up rather than
scope-creeping this ticket): `reconciliation_pass` still runs the same
CIK/CRD-batched loop, still capped by the same `remaining`, and -- by
design, isolated from cursor state -- still always restarts from the
beginning every call. If reconciliation's own `target_per_type` is ever
hit in practice, it would have the *identical* structural gap this ticket
fixed for the ordinary incremental pass, just on the monthly backstop
path. No live evidence yet that reconciliation is actually capped this
way in prod (it may run with a much larger budget, or complete within its
window today) -- needs its own live check before deciding whether it's a
real problem worth a dedicated ticket.

Tests: 4 new in `tests/mdm/test_pipeline_relationships.py`
(`TestInstitutionalHoldsResumableCursor`, `TestManagesFundResumableCursor`)
-- a capped run persists the cursor (not the watermark) and a follow-up
call resumes at exactly the unswept CIK/CRD range without rescanning
already-covered ground (asserted directly against the stub's recorded
query params, not just the row counts), plus a reconciliation-pass
isolation test for each type. Full `tests/mdm/` suite green (695 passed).
`022_relationship_derivation_checkpoint_cursor.sql`'s DDL has not been
run-verified against a live Postgres instance in this session (no local
Postgres was reachable in this sandbox) -- only its SQLAlchemy-model
equivalent, via SQLite's `Base.metadata.create_all`. Both statements
(`ALTER COLUMN ... DROP NOT NULL`, `ADD COLUMN IF NOT EXISTS`) are
standard, idempotent Postgres DDL already used elsewhere in this same
migrations directory, but a live `mdm migrate` run against prod (or at
minimum a local Postgres smoke test) is still the honest bar before
calling this migration itself verified, per this repo's own repeated
"migration exists ≠ migration applied/verified" lesson.

## 3-axis code review findings and fixes

Ran the mandatory 3-axis `/code-review` (Standards/Spec/GoF) on the diff
before committing. Two axes found real, must-fix issues -- both fixed,
both re-verified with new tests, full write-up in CLAUDE.md's own new
"INSTITUTIONAL_HOLDS/MANAGES_FUND capped-restart watermark 5-whys" entry
(added as part of closing the Standards axis's own finding that this fix
lacked the documented-there write-up its own severity warrants):

- **Spec axis, critical:** `advance_relationship_watermark`'s upsert guard
  (`WHERE watermark_value < excluded.watermark_value`) never fires when
  the existing row's `watermark_value` is NULL -- exactly the state
  `record_relationship_sweep_progress` leaves a row in after every
  multi-call sweep's first partial batch, i.e. the common case this
  ticket exists to fix. Reproduced independently before fixing. Fixed by
  widening the guard to also match a NULL existing value.
- **Spec axis:** the first draft unconditionally suppressed watermark
  writes during `reconciliation_pass`, an unstated regression versus
  every other relationship type (which still advance during
  reconciliation) and versus these two types' own pre-existing behavior.
  Fixed: reconciliation now advances the watermark when its own sweep
  completes without being capped (matching original behavior), and
  withholds the advance only when reconciliation itself gets capped
  (avoiding reintroducing this exact bug on the reconciliation path).
- **GoF axis:** the sweep-completion dispatch logic was duplicated
  near-verbatim between `_derive_institutional_holds` and
  `_derive_manages_fund`. Extracted into a shared
  `_finish_relationship_sweep` helper (also the natural place to fix the
  reconciliation regression above, once).
- **Standards axis:** flagged the missing 5-whys write-up (fixed, see
  CLAUDE.md) and the lack of a real-Postgres integration test for
  migration 022 (acknowledged, not fixed -- no local Postgres was
  reachable in this sandbox; remains an open verification gap, see below).

New tests: 3 in `tests/mdm/test_relationship_checkpoint.py` (new file --
direct, function-level coverage of `relationship_checkpoint.py`, proving
the NULL-guard fix and that it doesn't loosen the original
never-regress-a-real-value contract), 2 in
`tests/mdm/test_pipeline_relationships.py` proving the reconciliation
watermark fix (completes → advances, capped → doesn't). Full `tests/mdm/`
suite green (700 passed) after all fixes.

**Not yet done:** commit, migration 022 run-verified against a real
Postgres instance (no local Postgres reachable in this sandbox -- see
CLAUDE.md's new entry for detail), build, deploy, or any live prod
verification. Tickets 02/03/05 (IS_INSIDER/EMPLOYED_BY deactivation,
backfill) remain blocked on this ticket and are still open.
