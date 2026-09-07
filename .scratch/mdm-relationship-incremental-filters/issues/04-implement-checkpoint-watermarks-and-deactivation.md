Type: task
Status: resolved (2026-09-07)
Blocked by: 02

**Spawned by:** the map's own "Not yet specified" note calling for an execution
ticket for Ticket 02's locked design, plus a same-day follow-up grilling
exchange (outside this map, in the main session) that additionally scoped a
**deactivation** mechanism — "MDM inserts new and deactivates old" — across
`HOLDS`/`COMPANY_HOLDS`/`INSTITUTIONAL_HOLDS`. Ticket 02 only ever decided the
watermark/filtering half; deactivation is a new decision recorded here for the
first time.

## Question

Implement Ticket 02's locked watermark design (checkpoint table + migration +
per-type wiring) and a new deactivation mechanism for `HOLDS`/`COMPANY_HOLDS`/
`INSTITUTIONAL_HOLDS`, so a steady-state `mdm infer-relationships` run costs
minutes against `INSTITUTIONAL_HOLDS`'s 6.8M-row `sec_thirteenf_holding`
regardless of total table size, not hours.

## Answer

Implemented in two sequenced commits on `claude/mdm-relationship-incremental-derivation`
(branched fresh off `main`, not the existing `claude/bookkeeping-nplus1-fixes`
branch, per this repo's usual "each unrelated change gets its own branch" rule).

### Corrections to Ticket 02's design, found during implementation

1. **`ISSUED_BY` deferred — no valid watermark column exists.** Ticket 02's own
   text ("the natural accession-number-based ordering key everywhere else that
   reads a silver table") doesn't actually cover `ISSUED_BY`: it reads MDM's own
   Postgres `mdm_security` table directly, not silver. Checked
   `MdmEntity.updated_at`/`MdmSecurity.valid_from` as candidates — neither is
   bumped by `SecurityResolver`'s `sec_row.issuer_entity_id = issuer_entity_id`
   assignment (no `onupdate=` anywhere in `database.py`), so it doesn't track
   "when did this security's issuer get linked" at all. Also low-value: this
   table has ~3,143 matching rows (Ticket 01's inventory) — an unbounded scan
   here costs milliseconds, not hours, so there's no real performance problem
   to solve. Deferred pending either a schema change (dedicated
   `issuer_linked_at` column) or a decision that it's not worth one — not
   implemented this ticket.
2. **`EMPLOYED_BY` needs two independent watermarks, not one.** Its two source
   sub-queries (`sec_executive_record`, `sec_employment_event`) are
   independent tables with independent `ingested_at` columns, not a single
   joined query — one checkpoint row per relationship type can't represent
   both. Checkpoint table keyed on `checkpoint_key` (defaults to the bare
   `rel_type_name`; `"EMPLOYED_BY:exec"`/`"EMPLOYED_BY:event"` for this one
   type) rather than `rel_type_name` alone, to carry this without a schema
   change if a future type needs the same split.
3. **Critical: the MDM Reconciliation Backstop must bypass every watermark,
   or it stops being a safety net.** `run_reconciliation_backstop()` calls
   `MDMPipeline.run_all(limit=None, reconciliation_pass=True)`, which reaches
   `derive_relationships(target_per_type=None)` at the same call site the
   ordinary `mdm-infer-relationships` step uses — `reconciliation_pass` was
   never threaded that far before this ticket. Any row a watermark-filtered
   run permanently skips for a **transient** reason (its person/company
   entity not yet resolved this run, later resolved by a subsequent run) would
   never be retried by ordinary incremental runs once the watermark moves past
   its accession/timestamp — the backstop's entire stated purpose (change-
   propagation Ticket 50, monthly full-universe re-derivation) is to catch
   exactly this class of gap. Without this fix, the backstop would have
   silently inherited the same watermark filter and skipped the same rows for
   the same reason, forever. Fixed by threading `reconciliation_pass` through
   `derive_relationships()` → `_derive_relationship_type()` → each watermarked
   `_derive_*` method, which now treats the watermark as absent (scan
   everything) whenever `reconciliation_pass=True` — restoring the exact
   pre-this-ticket full-scan behavior for the backstop's own call shape, while
   still advancing the checkpoint afterward (harmless: whatever the
   reconciliation pass just fully re-scanned genuinely is the new high-water
   mark).

### Watermark design (6 of the 7 scoped types; `ISSUED_BY` deferred per #1 above)

- New table `mdm_relationship_derivation_checkpoint` (migration
  `021_relationship_derivation_checkpoint.sql`, plain additive table, same
  no-owner-role shape as `020_mdm_pipeline_lease.sql`): `checkpoint_key` PK,
  `rel_type_name`, `watermark_column`, `watermark_value` (TEXT — both
  accession-number strings and ISO8601 timestamps compare correctly
  lexicographically, avoiding a polymorphic-value-type table), `updated_at`.
- No checkpoint row for a type/key means "scan everything" (advisor's item 1)
  — every watermark lookup is `Optional[str]`, and every watermarked query's
  `WHERE` clause is only added when the lookup returns non-`None`.
- Checkpoint only advances to the high-water mark of rows **actually
  iterated** in the processing loop (tracked incrementally, row by row, before
  any `remaining`-budget early break) — never to the max of the whole fetched
  window when a budget truncated it short (advisor's item 2). A row skipped
  for a legitimate business reason (unresolved entity, corporate-owner
  mismatch, already-existing relationship) still counts as "iterated" and
  advances the watermark past it during an **ordinary** run — the
  `reconciliation_pass` bypass above (#3) is what keeps that permanent-skip
  risk bounded to at most one backstop cycle, rather than "fix the case
  individually per type."
- Checkpoint write goes through the same worker session each `_derive_*` call
  already uses (`self.session`), so it commits atomically with that type's own
  relationship writes at the existing `worker_session.commit()` call in
  `derive_relationships()`'s `_derive_one` closure — no new commit point, no
  new crash window (mirrors this repo's own "Bookkeeping checkpoint could
  outrun silver publish on crash" lesson: never let a checkpoint commit
  separately from the work it claims to represent).
- Per-type watermark column: `accession_number` (`IS_INSIDER`, `HOLDS`,
  `COMPANY_HOLDS`, `MANAGES_FUND`'s silver pair) or real `ingested_at`
  (`INSTITUTIONAL_HOLDS`'s pair, `EMPLOYED_BY`'s pair) — matches Ticket 02's
  decision exactly for the 6 implemented types.
- A caller-scoped call (`issuer_ciks` set, e.g. Ticket 21's insider-smoke path)
  skips the watermark entirely, mirroring the pre-existing precedent for the
  growing-window LIMIT ("existing universe totals are unrelated to this
  slice") — a targeted resync wants that issuer's full history rescanned, not
  whatever the global watermark says.

### Deactivation design

- **`HOLDS`/`COMPANY_HOLDS`:** in-row signal. A transaction row with
  `shares_owned_after == 0` (guarded: `None`/NULL is not zero — the field is
  nullable and already routed through `_json_property`) closes the matching
  active relationship via the existing `close_relationship_version` helper
  (`edgar_warehouse/mdm/graph.py`) — the same mechanism `AUDITED_BY` already
  uses for "new filing implies the old relationship ended." Guards a
  zero-then-later-nonzero sequence within the same batch (a security fully
  sold then re-acquired) by closing on the zero row and letting
  `ensure_relationship`'s own existing-version handling open a fresh version
  on the later non-zero row, rather than assuming monotonic decline.
- **`INSTITUTIONAL_HOLDS`:** two-phase cross-period diff, mirroring
  `_derive_manages_fund_batch`'s **already-existing** (and previously
  unnoticed by this map) `close_relationship_version`-based expected-targets
  comparison almost verbatim. Phase 1 (watermark-filtered): identify which
  managers (CIKs) have newly-watermarked 13F rows this run. Phase 2 (**not**
  watermark-filtered — advisor's item 3): for each such manager, re-query that
  manager's single latest true `(cik, period_of_report)` (reusing the
  existing `amendment_type = 'restatement'` exclusion already in
  `_derive_institutional_holds`'s `base_sql`) with no watermark bound at all,
  collect its full CUSIP set, and close any of that manager's currently-active
  `INSTITUTIONAL_HOLDS` relationships whose security isn't in that set. Using
  the watermark-filtered rows' own CUSIP set for the diff (instead of a fresh
  full re-query) would silently treat any security whose holding row happened
  to fall before the watermark boundary as "no longer held," even though the
  manager's real current 13F still reports it.

### Sequencing

Two commits, in order: (1) checkpoint table + migration +
`reconciliation_pass` threading + watermark wiring for the 6 types, (2)
deactivation for all three in-scope types. Not combined into one commit —
the deactivation logic reads the watermark's "which managers changed" output,
so debugging both halves at once against each other was avoidable risk for no
benefit; also, the watermark half alone is what answers the user's original
stated complaint (runtime, not correctness), so it's the half worth having
shipped first if anything interrupts the rest.

Full per-type code citations, test files, and deploy note (this migration
will not reach prod on deploy — needs an explicit `mdm migrate` via
`edgartools-prod-mdm-utility`, `{"mode": "mdm_migrate"}`, per this repo's own
repeatedly-documented migration-application gap) are in the commit messages
on `claude/mdm-relationship-incremental-derivation`, not duplicated here.
