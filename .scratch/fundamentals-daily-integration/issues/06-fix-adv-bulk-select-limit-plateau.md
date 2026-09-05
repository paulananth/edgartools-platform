# 06 — Fix `resolve_advisers_bulk`/`resolve_funds_bulk`'s unordered `LIMIT` plateau

Type: task
Status: resolved (2026-09-05)

**Blocked by:** none — independent of tickets 01-04 (different tables,
different subsystem: MDM adviser/fund resolution, not
`sec_financial_fact`/`sec_thirteenf_holding`/`sec_earnings_release`).

## Origin

Raised in this session's grilling round on "is ADV wired for diff
processing into `daily_incremental`." Originally filed as
[release-readiness Ticket 100](../../release-readiness/issues/100-adv-bulk-select-limit-plateau-on-restart.md)
and left unresolved there pending confirmation of live impact — that
confirmation is now done (see below), and the user chose to fix it here
rather than under release-readiness, alongside this map's other
`daily_incremental` incremental-scoping work.

## Confirmed live impact

`daily_incremental`'s `RunMdmChain` calls `mdm mastering --entity-type all
--limit 100` every day (`MDM_RUN_LIMIT` default 100,
`deploy-aws-application.sh:1882`). `MDMPipeline.run_all(limit=100)`
forwards that same `limit` straight into `run_advisers(limit=limit)` and
`run_funds(limit=limit)` (`pipeline.py:2065,2073`) — unlike
`run_companies`, which already got the Ticket 94 growing-window fix.

`resolve_advisers_bulk`/`resolve_funds_bulk` (`edgar_warehouse/mdm/adv_bulk.py`)
build their source query as:

```python
sql = "SELECT * FROM sec_adv_filing"       # or sec_adv_private_fund
if limit:
    sql += f" LIMIT {int(limit)}"
```

No `ORDER BY`. No exclusion of already-resolved identities in the query
itself — `_existing_source_ids` only dedupes *after* the fetch, turning an
already-seen row into a no-op rather than freeing a slot in the window for
a genuinely new one. On a stable table-scan order, every daily call re-reads
the same first ~100 rows: new advisers/funds beyond that window can never
be reached by `daily_incremental`'s bounded `mdm mastering` call — only an
unlimited `mdm run --entity-type all` (never invoked automatically) would
reach them.

## What to build

Port the exact fix already proven for `run_companies`
(release-readiness Ticket 94, `pipeline.py:427-455`): reuse the existing
`_bounded_relationship_sql` static helper (over-fetches a window sized to
`existing_count + max(limit * MULTIPLIER, MINIMUM)`), fetch with a stable
`ORDER BY`, exclude already-resolved identities, then cap at `limit`
genuinely-new rows.

- **Advisers**: identity is CRD (`by_crd`, already computed in
  `resolve_advisers_bulk`) with an accession-number fallback for CRD-less
  filings. `already_resolved` = the CRD keys already in `by_crd` (adapt:
  currently built from `existing_advisers`, same data, just needs sizing
  the fetch window on its count instead of an unbounded `LIMIT`).
  `ORDER BY` needs a stable key covering both identity branches — e.g.
  `ORDER BY crd_number NULLS LAST, accession_number` — confirm this doesn't
  split filing rows for the same identity in a way that breaks
  `_latest_by_identity`'s "latest wins" semantics within one fetched
  window (it operates on whatever the query returns, so all rows for a
  given identity present in the source table need to be fetchable in the
  same or a growing window, same guarantee `run_companies` already relies
  on for CIK).
- **Funds**: identity is `private_fund_id` (pfid) with an
  accession+fund_index fallback (`by_pfid`, already computed). Same
  pattern: `already_resolved` from `by_pfid` keys, stable `ORDER BY`
  (e.g. `ORDER BY private_fund_id NULLS LAST, accession_number,
  fund_index`), growing window via `_bounded_relationship_sql`.
- Note the adjacent, already-fixed fund-dedup history
  (`e6fc0626`, "re-key fund bulk resolution's dedup to accession-based, not
  pfid," change-propagation Ticket 42) — that fix changed which key
  *dedupes* a row for the `MdmSourceRef`/change-log path, not the
  `LIMIT`/`ORDER BY` shape this ticket fixes; keep both working together,
  don't revert Ticket 42's accession-based dedup while porting this fix.

## Tests

Mirror `tests/mdm/test_run_companies_bounded_limit_progress.py`'s pattern
exactly — a real `SilverDatabase`-backed DuckDB fixture (not the
substring-matched `StubSilver`, which ignores `LIMIT`/params entirely and
would silently mask this exact bug — Ticket 94's own documented trap):

- Cumulative progress across repeated calls: 3 successive `limit=N` calls
  against a fixture universe larger than `N` advisers/funds resolve
  strictly more identities each call, reaching full coverage without
  waste or plateau.
- Bounded-cost-per-call contract still holds: a single call never resolves
  more than `limit` genuinely-new identities.
- Clean termination once the universe is fully resolved (no error, no
  infinite growth of the fetch window).
- A companion test proving `_latest_by_identity`'s "latest filing wins"
  semantics are unaffected by the new `ORDER BY` (a CRD/pfid with multiple
  filing rows still picks the correct latest one).

## Acceptance

- [x] `resolve_advisers_bulk` and `resolve_funds_bulk` both use the
      growing-window pattern; repeated `mdm mastering --entity-type all
      --limit 100` calls against a real multi-hundred-adviser/fund fixture
      make cumulative progress instead of plateauing.
- [x] New tests pass; full `tests/mdm/` suite green, no regressions.
- [x] release-readiness Ticket 100 updated to point here (done — see its
      own Answer).
- [x] `/gof-refactor-reviewer` consulted before editing `adv_bulk.py`
      (repo hard rule).
- [x] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.

## Answer

**Design followed the plan exactly, with two additions surfaced by review
(below).** `/gof-refactor-reviewer` was consulted before implementing
(prompt and full transcript in this session's record): verdict was to
extract the growing-window helper into a new shared module rather than
duplicate it a 6th/7th time or reach into `MDMPipeline` across the
established local-import circular-dependency boundary.

**Implementation:**
- New `edgar_warehouse/mdm/bounded_fetch.py` — `bounded_source_sql(sql,
  remaining, existing=0)`, the exact logic previously private to
  `MDMPipeline._bounded_relationship_sql` (pipeline.py), extracted so a
  module with zero dependency on either `pipeline.py` or `adv_bulk.py` can
  be imported by both without reintroducing the circular import
  `pipeline.py`'s local/deferred `adv_bulk` imports already exist to avoid.
  `pipeline.py`'s `_bounded_relationship_sql` is now a one-line delegate,
  kept only so its 5 existing in-class call sites don't need to change.
- `edgar_warehouse/mdm/adv_bulk.py`: `existing_advisers`/`by_crd`/
  `unclaimed_by_cik` (advisers) and `advisers`/`adviser_by_crd`/
  `adviser_by_accession`/`existing_funds`/`existing_funds_by_entity_id`/
  `by_pfid` (funds) moved before the source fetch so their counts can size
  the growing window. New shared helper `_bounded_unresolved_rows(silver,
  base_sql, order_by_sql, limit, existing_count, exclude)` — added during
  the GoF review pass below, not in the original plan — used by both
  functions instead of each inlining its own near-identical fetch/filter
  block. Advisers: `ORDER BY crd_number NULLS LAST, accession_number`,
  excluding CRDs already in `by_crd`. Funds: `ORDER BY private_fund_id
  NULLS LAST, accession_number, fund_index`, excluding pfids already in
  `by_pfid`. A row with no CRD/pfid (accession-fallback identity) always
  passes the exclusion filter — no cheap way to know an accession-keyed
  identity was already resolved without a second round trip, and
  occasionally re-fetching one is harmless since `_existing_source_ids`
  already makes re-processing an already-seen accession a no-op.
  `limit=None` (today's only unbounded path, `mdm run --entity-type all`
  with no `--limit`) is unchanged: no `ORDER BY`, no filtering, fetch
  everything.

**`/code-review` (3 axes) findings and disposition:**
- **Standards:** no hard violations. Two judgement calls noted, both
  accepted as-is: a stale constant name (`_RELATIONSHIP_SOURCE_LIMIT_*` in
  `bounded_fetch.py`, kept since the module is still fundamentally about
  relationship/source-limit windowing) and the pre-fix duplicated
  fetch/filter shape (superseded by the GoF fix below before this ticket
  closed).
- **Spec:** one real gap — the ticket's own Tests section asked for a
  "latest filing wins" companion test covering *both* CRD and pfid; the
  first draft only had the adviser one. **Fixed**: added
  `test_latest_filing_still_wins_under_a_bounded_window` to
  `TestFundBoundedLimitMakesCumulativeProgress`, asserting on
  `fund_type`/`aum_amount` rather than `canonical_name` (fund names run
  through `MDMRuleEngine.normalize_name`'s legal-suffix stripping, which
  drops the literal word "Fund" — a name-based assertion would have tested
  normalization, not latest-wins ordering; caught by running the test
  before fixing the assertion).
- **GoF:** one real, evidenced finding — `resolve_advisers_bulk`/
  `resolve_funds_bulk`'s new limit-handling blocks were near-identical
  duplicates, and this exact file has already shipped two prior bugs where
  a fix landed in one of these two sibling functions and not the other
  (commits `ee62a968`, `e6fc0626`). **Fixed**: extracted
  `_bounded_unresolved_rows` (see Implementation above) before this ticket
  closed, rather than filed as a fast-follow — the evidence of prior
  same-file divergence made it not worth leaving open.

**Tests:** `tests/mdm/test_adv_bulk_bounded_limit_progress.py` (new, 8
tests — 4 adviser, 4 fund: cumulative-progress-across-3-calls,
single-call bounded-cost, fully-resolved-universe-is-a-no-op, and
latest-filing-wins-under-a-bounded-window, one set per entity type).
Confirmed red-before/green-after via `git stash` against the pre-fix code
(4 of 7 failed at that point, before the fund latest-wins test was added;
all now pass). Existing `tests/mdm/test_adv_bulk_resolution.py` (12 tests,
stub-silver-based, exercise only the unbounded path) and
`tests/unit/test_merge_adv_bulk.py` (4 tests) pass unchanged — confirming
the `limit=None` path is untouched. Full `tests/mdm/` suite: 562 passed
(up from 561 pre-fix, the +1 being the new fund latest-wins test), same 3
pre-existing unrelated `fastapi`-import-collection module errors excluded
(`test_runtime_ops.py`/`test_api.py`/`test_temporal_graph_queries.py`,
already documented in CLAUDE.md). Full repo suite: 3032 passed, 8 failed
(same pre-existing, unrelated Postgres-integration schema-drift gaps
documented elsewhere in CLAUDE.md), 6 skipped — no new failures.

Not yet committed/pushed/PR'd as of this Answer — per this repo's standing
rule, only on explicit user ask.
