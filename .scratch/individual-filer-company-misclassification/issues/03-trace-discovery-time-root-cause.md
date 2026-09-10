Type: task
Status: resolved
Blocked by: 01

## Question

Pin down the exact call site that first decides an individual/insider CIK
(entity_type 'other' in SEC's own submissions data) is worth fetching a
full submissions.json for and feeding into `stage_company_loader`/
`merge_company`. Leading candidate: `daily_incremental`'s SEC-daily-index
"impacted CIK" discovery, since SEC's daily index lists an ownership-form
accession under both the issuer's and every reporting owner's own CIK.
Needs tracing through the actual code, not assumed.

## Answer

Traced live through `edgar_warehouse/application/warehouse_orchestrator.py`
(not assumed), confirmed at every hop:

1. `_load_daily_index_for_date` extracts `impacted_ciks` as
   `_dedupe_ints([int(row["cik"]) for row in rows if row.get("cik") is not
   None])` -- every distinct CIK appearing in that day's SEC master index,
   with zero filter on role (issuer vs. reporting owner) or form type. SEC's
   daily index lists an ownership-form accession under the reporting
   owner's own CIK, so an individual insider's Form 4/144/13G filing puts
   their personal CIK straight into this list.
2. `_seed_silver_tracking_status(bookkeeping, impacted_ciks,
   tracking_status="active")` unconditionally marks every one of those
   CIKs `active` in `sec_company_sync_state` -- this happens *before* any
   submissions.json is fetched, so entity type genuinely isn't knowable
   yet at this point.
3. `_filter_ciks_to_universe` -- despite its name -- is a no-op safeguard
   for freshly-discovered CIKs: it only excludes CIKs *not already*
   tracked-active, and step 2 just marked them active one line earlier.
   It filters paused/retired companies back out of an incremental run, not
   whether a CIK belongs in the company universe at all.
4. Only once the per-CIK submissions.json is actually fetched does
   `stage_company_loader` (`edgar_warehouse/loaders/
   bronze_submission_extractors.py`) see `payload.get("entityType")` --
   and it correctly stores it into the `entity_type` field, but nothing
   gates the write on that value. `merge_company()` (`silver_store.py`)
   writes the row to `sec_company` unconditionally.

**The correct, minimal fix point is step 4** -- it is the only place in
the whole chain where `entity_type` is actually known; steps 1-3 can't
cheaply distinguish company vs. individual without the fetch step 4
already does. The fix is to skip writing the `sec_company` (and
presumably paired address/former-name) rows when `entityType` isn't a
real reporting-company type (`'operating'`/`'investment'`, per the live
`SEC_COMPANY` breakdown in Ticket 01 -- `'other'` is the individual-filer
value).

**Compounding cost issue, not just correctness:** because step 2 marks the
CIK `active` in tracking state regardless of what step 4 later finds,
these individuals stay in the tracked universe and get their *entire*
submissions.json re-fetched on every subsequent `daily_incremental` run
they show up in the daily index again for -- not a one-time mistake. A
complete fix should also downgrade/exclude `sec_company_sync_state`'s
tracking status once `entity_type` is known to be non-company, not just
stop the `sec_company` write.

Fix design (batching, whether to also touch `bootstrap-next`/`load_history`'s
own CIK-discovery path which may share this shape, and the actual code
change) is not done here -- this ticket was scoped to tracing the root
cause. Next: a fresh ticket to design and implement the fix.
