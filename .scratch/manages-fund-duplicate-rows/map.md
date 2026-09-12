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

- [Root-cause identical-evidence merge failure](issues/01-root-cause-identical-evidence-merge-failure.md) — This is a one-time historical event, not an ongoing bug: all 140,907 duplicate groups' active rows share the exact same `created_at` instant (2026-08-19 15:50:30 UTC), and zero groups have an active duplicate created after the 2026-08-21 CRD-batching refactor that superseded the old code path, despite 4,116 new rows written since. The exact mechanism inside the now-replaced old code wasn't conclusively pinned down (further root-causing dead code isn't a good use of time), but the practical, decisive evidence holds regardless. Confirmed distinct from `mdm-relationship-versioning-gap`'s 5 other affected types, which all show ongoing duplication spread across many days through 2026-09-08 — that map's already-diagnosed chain-versioning gap, not this one. Reshapes Ticket 02: may not need a code fix at all, just confirmation before going straight to backlog cleanup.
- [Decide write-time fix mechanism](issues/02-decide-write-time-fix-mechanism.md) — No code fix needed: 3+ weeks of clean production writes since the refactor is sufficient evidence, especially since the refactor's own structural change (per-batch priming + per-batch commits) is a plausible sufficient cause regardless of the exact old mechanism. Ticket 03 repurposed from "implement a fix" to a lightweight live-monitoring check (mirroring `mdm check-fence`'s precedent) as insurance against the unconfirmed mechanism. Ticket 04's backlog-cleanup design unaffected and no longer blocked on Ticket 03.
- [Implement and deploy write-time fix](issues/03-implement-and-deploy-write-time-fix.md) — Built as `mdm check-manages-fund-duplicates` (new `manages_fund_duplicate_monitor.py` + CLI subcommand + `mdm_utility` schedule/alarm wiring), mirroring `mdm check-fence`'s exact shape. Regression/backlog distinction uses a fixed `KNOWN_BACKLOG_CUTOFF` constant (2026-08-22) rather than a persisted baseline, since every known-backlog row is provably from 2026-08-19. Passed `/gof-refactor-reviewer` (pre-code) and the mandatory 3-axis `/code-review` (post-diff) with zero blocking findings on any axis.

## Not yet specified

(none — Ticket 01 confirmed this is isolated to MANAGES_FUND, not shared with the other 5 types)

## Out of scope

(none yet)
