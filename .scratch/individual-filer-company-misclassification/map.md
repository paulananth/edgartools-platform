# Individual filers misclassified as companies

## Destination

`sec_company` (and everything downstream: MDM `mdm_company`/`mdm_entity`,
gold company counts, dashboards) contains only genuine reporting companies
-- individual/insider filers (Form 3/4/5/144/Schedule 13D/13G filers who
never file as an issuer) are correctly excluded from the company universe
going forward, and the already-corrupted rows are cleaned up (reclassified
or removed) rather than left silently polluting every downstream consumer
of "the company universe."

## Notes

- Domain: `edgar_warehouse/silver_store.py` (`merge_company`, the sole
  writer of `sec_company`), `edgar_warehouse/application/
  warehouse_orchestrator.py` (`daily_incremental`'s CIK-discovery chain --
  `_load_daily_index_for_date` -> `_seed_silver_tracking_status` ->
  `_filter_ciks_to_universe`, confirmed the source, per Ticket 03; whether
  `bootstrap-next`/`load_history` shares the same shape not yet checked),
  and `edgar_warehouse/loaders/bronze_submission_extractors.py`'s
  `stage_company_loader` (builds the row `merge_company` writes, carries
  SEC's own `entityType` field through as `sec_company.entity_type` but
  nothing reads it as a filter).
- `/gof-refactor-reviewer` (CLAUDE.md hard rule) before any code change;
  full 3-axis `/code-review` (Standards/Spec/GoF) before any commit.
- Standing preference from the parent session: real measurements against
  live prod data, not estimates.
- Surfaced while investigating
  [mdm-relationship-versioning-gap's Ticket 10](../mdm-relationship-versioning-gap/issues/10-run-chain-aware-backfill-remaining-four-types.md)
  (extending the quarantine backfill to COMPANY_HOLDS) -- COMPANY_HOLDS'
  quarantine backlog turned out to be dominated by exactly this
  contamination, which is why that ticket paused on COMPANY_HOLDS
  specifically and split this off as its own map rather than trying to
  fix it inline.

## Decisions so far

- [Discovery: root cause + blast radius](issues/01-root-cause-and-blast-radius.md) — confirmed live against real prod Snowflake data (`EDGARTOOLS_SILVER.SEC_COMPANY`), not assumed. Sample proof: 3 well-known individuals (Mark Zuckerberg CIK 1548760, Jensen Huang CIK 1197649, Javier Olivan CIK 1564475) all have `sec_company` rows with `entity_type='other'`, zero real company-filing types (10-K/10-Q/8-K/etc.) in their filing history, exclusively ownership-related forms (3/4/5/144/SC 13G-A) — and none of the three appear in SEC's real `company_tickers.json` (10,407 legitimate entries), ruling out the standard ticker-based seed path as the source. Total blast radius: `SEC_COMPANY` has 64,924 `entity_type='other'` rows (vs. 7,009 `operating` + 1,758 `investment`); of those, 32,948 have a filing history that is *exclusively* ownership/144/13D/13G forms — i.e., confirmed individual filers, not companies, nearly 3x the size of the real company universe. `merge_company()` (`silver_store.py`) is confirmed to write whatever `stage_company_loader` hands it with zero filtering on `entity_type`, and `stage_company_loader` correctly carries SEC's own `entityType` signal through into the `entity_type` column — the value is captured but never acted on anywhere. The exact upstream CIK-discovery call site that first decides "fetch this CIK's submissions.json as a company" has not yet been pinned down to a specific function/line (candidate: `daily_incremental`'s daily-index "impacted CIK" sweep, since SEC's daily index lists an ownership-form accession under both the issuer's and every reporting owner's CIK) — this is the next open question, not yet a ticket (see "Not yet specified").

- [Decide cleanup strategy for misclassified rows](issues/02-decide-cleanup-strategy-for-misclassified-rows.md) — grilled with the operator. End state: these ~33K individuals should be correctly re-resolved as persons with real IS_INSIDER/HOLDS relationships, not just removed (confirmed live: none of the 3 sampled individuals have any `mdm_person` row today — this is a missing-resolution problem, not a duplicate-cleanup one). Cleanup waits until the discovery-time root-cause fix ships (otherwise the next `daily_incremental` run recreates the contamination). Mechanism: delete outright (not quarantine-flag, not in-place reclassify) — relies on the untouched raw ownership-filing data plus the fixed resolver to correctly re-derive each person afterward. Rollout: piloted on the 3 already-investigated CIKs before scaling to all ~33K.

- [Trace discovery-time root cause](issues/03-trace-discovery-time-root-cause.md) — traced live through `warehouse_orchestrator.py`, confirmed at every hop. `_load_daily_index_for_date` extracts `impacted_ciks` as every distinct CIK in the SEC daily index with zero filter on role/form-type (an ownership accession lists the reporting owner's own CIK). `_seed_silver_tracking_status` unconditionally marks every one `active` in tracking state *before* any submissions.json is fetched (entity type isn't knowable yet at this point). `_filter_ciks_to_universe` is a no-op safeguard for freshly-discovered CIKs despite its name — it only excludes CIKs *not already* tracked, and the seed step just tracked them one line earlier. Only once the per-CIK submissions.json is fetched does `stage_company_loader` see `entityType` — it's stored into `entity_type` correctly, but `merge_company()` writes the row regardless. **The fix belongs at that last hop** — it's the only point in the chain where entity type is actually known. Compounding cost issue found the same pass: because tracking status is set `active` before entity type is known, these individuals stay in the tracked universe and get their full submissions.json re-fetched on every subsequent `daily_incremental` run, not just once.

- [Implement discovery-time fix](issues/04-implement-discovery-time-fix.md) — both fixes landed at the single real choke point (`stage_submission`/`_apply_submission_snapshot_to_silver`, one caller for `daily_incremental`/`bootstrap-next`/`load_history` alike), sharing one new classification function (`is_reporting_company_entity_type`) so the write-skip and the tracking-status demotion (new `"non_company"` status, excluded by `_filter_ciks_to_universe`'s existing `active`-only filter) can't drift apart. Cleanup of the ~33K already-corrupted rows deliberately not done here (Ticket 02's decision). 4 new tests, full suite green (3182 passed). 3-axis `/code-review` clean, no hard findings.

## Not yet specified

- The discovery-time fix ([Ticket 04](issues/04-implement-discovery-time-fix.md))
  has shipped in code but is not yet deployed/live-verified in prod (no
  image rebuild has happened for this change as of this writing). Once
  deployed: execute the delete-and-re-derive cleanup decided in Ticket 02,
  piloted on the 3 known CIKs first, then at full ~33K scale. Not yet a
  ticket -- blocked on that deploy.
- Whether this same contamination reaches `EDGARTOOLS_GOLD.COMPANY` (the
  gold dynamic table) or dashboards that report "total tracked
  companies" — not yet checked; the investigation so far only confirmed
  silver (`sec_company`) and MDM (`mdm_company`).
- Cost impact: how much SEC API/S3/DuckDB-merge time has been spent
  ingesting ~33K individuals' full filing histories as if they were
  companies, across however many `daily_incremental`/`bootstrap-next`
  cycles have run since this started — not measured.

## Out of scope

(none yet)
