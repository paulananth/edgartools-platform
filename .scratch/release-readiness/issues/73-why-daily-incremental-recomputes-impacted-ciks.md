# Why does daily-incremental's RunWarehouseTask recompute impacted CIKs separately from ComputeIdentityRefreshWindow?

Type: research
Status: resolved

## Question

`ComputeIdentityRefreshWindow` and `RunWarehouseTask`'s `daily-incremental` command
both derive "which CIKs are impacted by the last 7 days" from the same SEC
daily-index window, independently, in the same execution. `ComputeIdentityRefreshWindow`
landed on 1,194 CIKs; `daily-incremental`'s own handler landed on 10,491 -- is the
second computation wasteful duplication that should reuse the first, or a genuinely
different scope?

## Answer

**Genuinely different scope, not wasteful duplication of the filtering.**

- `ComputeIdentityRefreshWindow` (`warehouse_orchestrator.py:2415-2430`) intersects
  the 7-day impacted-CIK union with `company_eligible_ciks =
  db.get_company_identity_ciks("active")` -- the narrow "active operating
  company / current SEC ticker" universe. That intersection is *why* it's the
  right (and only correct) input for Stage0's company-identity resolution.
- `daily-incremental`'s own handler (`warehouse_orchestrator.py:1140-1179`)
  intersects its own 7-day impacted-CIK union with `_filter_ciks_to_universe` ->
  `db.get_tracked_ciks("active")` (`warehouse_orchestrator.py:5302-5312`) -- the
  full active-tracked universe (~26K total; 10,491 filed something in this
  window). This legitimately includes Form 3/4/5 insiders, ADV investment
  advisers, and 13F institutional managers -- none of whom are
  "company-identity-eligible" but all of whom need their filings captured by the
  general artifact-capture pipeline.

Reusing `ComputeIdentityRefreshWindow`'s narrower 1,194-CIK set here would be
**incorrect**, not just wasteful -- it would silently drop insider/adviser/
institutional-manager filings from capture. The two computations serve different
purposes and cannot share a result via a simple substitution.

**Verified CIK is not company-only, with live evidence** (checked directly
against `form.20260728.idx`, the same real SEC daily-index file used elsewhere
this session): every SEC filer gets its own CIK on first filing, individual or
entity, not just public companies.
- Individual insiders: `4  ABERNATHY ROBERT E  1222888  20260728
  edgar/data/1222888/...` -- a person's name and CIK filing their own Form 4.
- Investment advisers: `edgar_warehouse/parsers/adv.py` accepts `cik` (the EDGAR
  filer id) as a field distinct from `crd_number` (the FINRA/IARD regulatory id,
  regex-extracted from the filing body) -- two separate identifier systems for
  the same adviser.
- 13F institutional managers: `13F-HR  4Thought Financial Group Inc.  1840261
  ... edgar/data/1840261/...` -- same pattern.

**What genuinely is duplicated:** both stages independently call
`_load_daily_index_for_date(force=True)` for the same 7 calendar days, re-fetching
and re-parsing the same SEC daily-index files from scratch each time. This part
*is* redundant -- but post-[ticket 68](68-batch-daily-index-filing-merge-inserts.md),
it costs ~2.8s total (7 files x ~0.4s), no longer worth engineering around.

## Not yet specified

Whether the 10,491-CIK submissions bronze capture phase itself (currently ~64
minutes, observed live on `daily-incremental-ticket70-verify-1785720814`) has a
further optimization opportunity is genuinely open -- not yet investigated
whether that pace is dominated by real, rate-limit-bound SEC network calls
(expected and not fixable) or by per-CIK cache-hit-checking overhead against
already-captured submissions (which would be a sixth instance of this session's
unbatched-per-row pattern, in `_capture_submission_bronze_snapshot`/
`_capture_submissions_main`). Needs a live breakdown (network_fetches vs.
silver_skips count, similar to the `catalog_network_fetches`/`catalog_silver_skips`
split already emitted elsewhere) before it's ticket-able.

## Done when

Done -- the "why recompute" question is answered from direct code reading, with
exact line references for both filter paths. The follow-on optimization question
is explicitly deferred to "Not yet specified," not guessed at.
