# MANAGES_FUND duplicate active rows

## Destination

Two parts, both required to close this out:

1. **Root-cause and fix why `ensure_relationship`'s identical-evidence
   merge check fails to dedupe `MANAGES_FUND` inserts**, eliminating the
   write-time source of new duplicate active rows.
2. **Decide (and if needed, execute) how the existing ~140,907-relationship_id
   backlog gets cleaned up** — a targeted dedup pass, or confirmed
   self-healing once the write-time bug is fixed. Not started until (1) is
   confirmed fixed, so the backlog doesn't regrow mid-cleanup.

## Notes

- Domain: `edgar_warehouse/mdm/pipeline.py` (`MDMPipeline._derive_manages_fund`/
  `_derive_manages_fund_batch`), `edgar_warehouse/mdm/graph.py`
  (`GraphSyncEngine.ensure_relationship`/`prime_relationship_type`/
  `_index_open_relationship_versions`, `relationships_conflict`).
- Discovered while grilling
  [mdm-relationship-versioning-gap Ticket 08](../mdm-relationship-versioning-gap/issues/08-redesign-quarantine-backfill-for-multi-version-chains.md),
  which explicitly ruled MANAGES_FUND out of its own scope and flagged it
  as needing its own future map — this is that map. That ticket's own
  stated root cause ("empty `properties` dict") was itself corrected
  during this map's charting session; see this map's Ticket 01 and the
  correction notes left on that map/ticket.
- **Live evidence gathered during charting (2026-09-12), via direct MDM
  Postgres queries** (`edgartools-prod/mdm/postgres_dsn` secret, piped
  straight into a throwaway script, DSN never printed):
  - The empty-properties fallback path (`source_system='mdm_backfill'`,
    the degenerate zero-ADV-data branch in `_derive_manages_fund`) wrote
    only **17 rows total** — nowhere near the 140,907-relationship_id
    scale of the real bug. Ruled out as the cause.
  - The real, live code path (`_derive_manages_fund_batch`) passes a full
    `properties` dict to `ensure_relationship` (`private_fund_id`/
    `source_filing_id`/`source_section`/`reporting_role`/
    `evidence_fingerprint`) — confirmed present since a 2026-08 commit
    (`869003da`) via `git log -L`, predating the wrong claim.
  - Sampled the 5 highest-duplication `relationship_id`s: every one has
    2-4 rows with **byte-identical** `properties`, `valid_from_date`,
    `valid_to_date`, `source_system`, `source_accession`, and
    `created_at` (matching to the microsecond — consistent with one
    Postgres transaction, since `NOW()` is transaction-time not
    statement-time).
  - Cross-checked one sample's silver source
    (`EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_ADV_PRIVATE_FUND`, `filing_id
    2117808`/`private_fund_id 805-4753683614`): exactly **1** row. Not a
    source-data duplication issue — the silver layer has exactly the
    evidence it should; the duplication happens between silver and the
    MDM Postgres write.
  - `run_id` is NULL on all sampled rows (not populated for this call
    path) — not independently useful, but consistent with everything
    happening in one untracked run.
- `_derive_manages_fund_batch`'s own duplicate-diff/deactivation logic
  (`close_relationship_version` keyed on `expected_targets_by_adviser`)
  already exists in this method and looks structurally sound on a read —
  the bug is in `ensure_relationship`'s own identical-evidence path, not
  (as far as this session's reading found) an obviously missing dedup
  step in the caller.
- Signature that distinguishes this from `mdm-relationship-versioning-gap`'s
  own bug class: that map's affected types (INSTITUTIONAL_HOLDS,
  COMPANY_HOLDS, EMPLOYED_BY, IS_INSIDER, HOLDS) have a real, sometimes-large
  quarantined-row fraction alongside their duplicated-active-row counts
  (e.g. INSTITUTIONAL_HOLDS: 63,591 duplicated, 7,966 also quarantined —
  12.5%). MANAGES_FUND's ratio is 140,907 duplicated, 3,960 also
  quarantined — 2.8%, and this session's samples suggest the true
  never-quarantined fraction is even higher (every sample was a clean,
  no-conflict duplicate). This is why Ticket 03 (Decision so far, once
  resolved) scoped the root-cause search to `_derive_manages_fund`'s own
  code rather than assuming a shared `ensure_relationship`-wide defect.

## Decisions so far

(none yet — charting session only; first ticket is research, not yet resolved)

## Not yet specified

- Whether any of the other 5 relationship types
  (INSTITUTIONAL_HOLDS/COMPANY_HOLDS/EMPLOYED_BY/IS_INSIDER/HOLDS) share
  whatever mechanism is found to cause MANAGES_FUND's bug — not assumed,
  since the quarantine-ratio signature looks distinct (see Notes above).
  Worth a quick check once Ticket 01's root cause is known, not before.

## Out of scope

(none yet)
