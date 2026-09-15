# Silver Merge-Engine Migration

## Destination

`silver_store.py`'s DuckDB-specific merge/dedup engine (`SilverDatabase.merge_financial_facts`/
`merge_accounting_flags`/`merge_financial_derived`/`mark_entity_facts_refreshed`, and the
equivalent methods for `per-filing`/`thirteenf`/`company-identity` modes — temp staging tables,
`QUALIFY ROW_NUMBER() OVER (...)` window functions, `ON CONFLICT ... DO NOTHING` upserts) is
reimplemented on a non-DuckDB engine, table by table, until no production write path depends on
DuckDB for merge/dedup compute. Reaching the destination means `duckdb` can finally come out of
`pyproject.toml`/`uv.lock` (DuckDB Retirement Cutover Ticket 20's last deferred checklist item),
and "DuckDB retirement" as an effort is actually complete rather than permanently "in progress."

## Notes

This effort **carries execution into the map**, per wayfinder's override — the destination
is a code migration (per-table, expand/migrate/contract), not a design document to hand off,
so tickets past the engine/order decision (Ticket 01) are build slices, not open decisions,
except where a table's specifics genuinely need a fresh design pass.

- Parent decision: [DuckDB Retirement Cutover Ticket 20](../duckdb-retirement-cutover/issues/20-decide-silver-store-merge-engine-fate.md)
  — confirmed live (via `bootstrap_fundamentals.py`'s `LandingExportBuffer`, Ticket 18) that the
  DuckDB merge engine's output is genuinely load-bearing, not orphaned. Decided: reimplement,
  not keep permanently — but as a real migration project, not a single big-bang engine swap.
- Explicit precedent to follow, not reinvent: the bootstrap-fundamentals-crash-resume map's
  `mark_entity_facts_refreshed` → BookkeepingStore/Postgres move — expand (new mechanism lands
  alongside the old), migrate (callers switch table by table), contract (old DuckDB path
  removed once nothing depends on it). This map generalizes that same pattern from one marker
  to the full merge/dedup engine.
- Consult `/gof-refactor-reviewer` before any production-code edit (CLAUDE.md hard rule).
- Run the full 3-axis `/code-review` (Standards/Spec/GoF) before any PR is ready (CLAUDE.md
  hard rule).
- `mark_entity_facts_refreshed` stays on the bootstrap-fundamentals-crash-resume map — the
  scope-convergence idea noted here previously was tried and reverted the same day (see
  Ticket 01's own CORRECTION section); this map's own Tickets 02/03 are unrelated new
  tickets (the merge-engine build slices), not the marker.
- **Overlap discovered 2026-09-12: this map's destination question was largely already
  decided at a higher level.** The `duckdb-retirement` wayfinder map (`.scratch/duckdb-
  retirement/`, decision-only, resolved/handed off 2026-08-28) already decided the write
  path retires to "Snowflake landing zone only" — no replacement local merge engine of any
  kind — and its implementation arm, `duckdb-retirement-cutover`, already shipped that
  cutover live (Ticket 10, 2026-09-12). This map (spawned from `duckdb-retirement-cutover`'s
  own Ticket 20) was chartered without checking whether its parent map had already settled
  the question one level up. If Ticket 01's "delete, don't port" recommendation is confirmed,
  this map's remaining scope shrinks to cleanup (deleting now-dead merge calls table by
  table) rather than a genuine engine migration — worth revisiting whether this map should
  keep existing separately or fold into `duckdb-retirement-cutover`'s own remaining tickets.

- **Scope widened 2026-09-13 (grilled, accepted):** beyond the merge engine, this map now
  carries everything between "entity-facts trio landing-only" and "`duckdb` out of
  `pyproject`" — the remaining writers (Tickets 04–06), the confirmed-dead local readers
  (Ticket 07), the DuckDB-vs-Snowflake parity tooling (Ticket 08), and the final dependency
  removal (Ticket 09). Cross-map blockers wired on Ticket 09 rather than re-decided here:
  duckdb-retirement-cutover Ticket 21 (old canonical S3 objects) and the
  bootstrap-fundamentals-crash-resume marker move.
- **The five `drive-*-discovery` drivers are NOT deleted by this map.** They open local DuckDB
  and their publish is a no-op, so their writes go nowhere today — but the change-propagation
  map (Ticket 27, "contract legacy acquisition bypasses") plans to retire the legacy capture
  path *in their favour*. Their DuckDB dependency disappears as a side effect of Tickets 04–06
  (every `merge_*` they call becomes landing-only); wiring a `LandingExportBuffer` into them is
  that map's job, noted there.

## Decisions so far

- [Decide silver_store.py's DuckDB merge-engine fate](../duckdb-retirement-cutover/issues/20-decide-silver-store-merge-engine-fate.md) — reimplement on another engine (not keep DuckDB permanently), scoped as a real per-table migration project, not a single engine swap. Decided 2026-09-12.
- [Choose the replacement engine and migration order](issues/01-choose-replacement-engine-and-migration-order.md) — resolved 2026-09-13 after three rounds (two "confirmed dead compute" claims and one Postgres-scratch-store answer were each found wrong before code was written — see the ticket's own history). Final shape: the whole entity-facts trio (`sec_financial_fact`, `sec_financial_derived`, `sec_accounting_flag`) is delete-and-passthrough to `landing_export`; the one in-process reader (`backfill_accounting_flags`) only ever re-read data the same per-CIK loop iteration had just produced from a full-history companyfacts payload, so its scoring moved in-memory instead of onto a store. No Postgres scratch store, no new Snowflake table. `mark_entity_facts_refreshed` stays off this map. `per-filing`/`thirteenf` confirmed to NOT share a read-back shape — delete-and-passthrough each, to be confirmed per table.
- [Delete `merge_financial_facts`'s local DuckDB write](issues/02-delete-merge-financial-facts-local-write.md) — resolved 2026-09-13. Landing-only via a shared `_record_landing_passthrough`; NOT NULL enforced by raising; `ingested_at` + validity trio stamped per write; acceptance read-back deleted (VERIFIED on record); DuckDB DDL kept.
- [Score accounting flags in memory; flags/derived landing-only](issues/03-postgres-scratch-store-for-derived-and-flags.md) — resolved 2026-09-13. Pure `score_accounting_flags` inside `run_bootstrap_entity_facts`'s per-CIK loop replaces `backfill_accounting_flags`/`update_accounting_flag_scores`; `retire_*_not_in_snapshot` deleted. Not yet live-verified.
- [Make the per-filing fundamentals tables landing-only](issues/04-per-filing-tables-landing-only.md) — resolved 2026-09-13. Five writers on `_record_landing_passthrough` with `ingested_at` stamped; old coercions kept at the call site. Also fixes NULL landing `ingested_at`, which hid these rows from MDM's EMPLOYED_BY watermark. Collapse keys verified. Not yet live-verified.
- [Make the 13F tables landing-only](issues/05-thirteenf-tables-landing-only.md) — resolved 2026-09-13. Both 13F writers on the passthrough with `ingested_at` stamped (fixes the same NULL-watermark gap for INSTITUTIONAL_HOLDS). Volume checked: 100k holdings record in 0.53 s and flush in 1.43 s, versus ~156 s for 20k rows on the old per-row DuckDB path; flush cost unchanged from before. Not yet live-verified on a large filer.
- [Make the submissions/artifact-path tables landing-only](issues/06-submissions-and-artifact-tables-landing-only.md) — split 2026-09-13 by a reader inventory into 06a–06d, because several of these tables are read back inside the same run. **06a resolved:** the ADV five, subsidiary/auditor evidence, PCAOB firm identities and the current filing feed are on the passthrough, stamped with `last_sync_run_id`. **06b resolved:** the four company submission tables too; `stage_submission`'s per-CIK DELETEs (local-only, never reached landing) are gone, the acceptance driver's company read-back settles on the recorded count, and the dead local readers are deleted. **06c resolved:** the ownership trio is on the passthrough; the silver-once skip's fallback to local owner rows is deleted (the durable bookkeeping parse run already covers it), not moved to Snowflake. **06d resolved:** filings, attachments and raw objects are landing-only, and their same-run readers get their answer from an in-run lookup inside `SilverDatabase` that keeps the old upsert's first-value/latest-write split per column ([ADR 0011](../../docs/adr/0011-same-run-silver-reads-from-recorded-rows.md)); not local DuckDB, the bookkeeping store or Snowflake. Found in implementation: release-mode Branch B reads these tables with raw SQL, which the lookup does not serve, so it now fails closed — [Ticket 11](issues/11-restore-release-mode-branch-b-same-run-reads.md). Tickers and filing text split into 06e. **06e resolved in code** (2026-09-14; live `seed-universe` verification owed): a straight landing-only switch; the ticker writer keeps its skip of rows without a `cik` or ticker, the filing-text writer its seven-field check; the uncalled ticker and filing-text readers and the now-unused `track_landing_rows`/`track_landing_row` decorators are deleted; the dormant reference-catalog driver keeps its read of the earlier ticker list unchanged (fog below). Reads meant for earlier runs keep today's behaviour; the apparently broken `targeted-resync --scope accession` is [Ticket 10](issues/10-restore-targeted-resync-accession-scope.md).
- [Delete the confirmed-dead local-DuckDB readers](issues/07-delete-confirmed-dead-duckdb-readers.md) — resolved in code 2026-09-14 with a corrected scope. `validate-data-quality` is deleted: it checked a frozen copy of the retired canonical DuckDB. `parse-adv-bronze` keeps only `--artifact`: its registry discovery and `already_parsed` gate read the always-empty local store. `relationship_bulk_load.py` (MDM's Snowflake reader) and `capture_parity.py` (Ticket 53's parity tool, already on the in-run lookup since 06d) were not dead local readers and are unchanged.
- [Delete `ShardedSilverReader` and `verify-resolver-input-parity`](issues/08-delete-sharded-reader-and-parity-tooling.md) — resolved in code 2026-09-14 with a corrected scope. Both `mdm verify-*-parity` commands, `mdm/silver_parity.py`, the DuckDB-reader helpers and the shard-hydrate helpers are deleted; cutover Tickets 19/21 rely on `table-reconcile`, not this tooling. `ShardedSilverReader` stays: `backfill-silver-landing-historical` still reads through it, and both go in Ticket 09.
- [Restore targeted-resync accession scope](issues/10-restore-targeted-resync-accession-scope.md) — resolved in code 2026-09-14. Confirmed broken by a local repro (no live run, user decision): `get_filing` only sees same-run rows. Fixed by reading every (accession, cik) row from `EDGARTOOLS_SILVER.sec_company_filing` and recording it before the unchanged resync steps; fails closed, pointing at cik scope, when silver has no row. Not yet run live.
- [Restore release-mode Branch B same-run reads](issues/11-restore-release-mode-branch-b-same-run-reads.md) — resolved in code 2026-09-14 by retiring release mode (user decision): the strict path of `one_click_data_refresh`, `reconcile-relationship-release`, every `--release-mode` path and the release-only helpers and scripts are deleted. It last ran 2026-07-25 and was broken at both ends (manifest freeze read the retired DuckDB file; Branch B raw SQL found nothing after 06d). Recurring mode keeps the shared retry and fail-closed logic. Takes effect on the next deploy.
- [Make the fundamentals markers landing-only](issues/12-fundamentals-markers-landing-only.md) — resolved in code 2026-09-14. `mark_fundamentals_accession_processed` and `mark_entity_facts_refreshed` are on the passthrough with a UTC timestamp stamped; both readers already query Snowflake silver. Replaces the crash-resume "marker move" as Ticket 09's blocker: DuckDB removal needs only this switch, not that map's per-CIK resume ledger. Live verification owed with Tickets 02/03's run.
- [`sec_company_ticker`'s DuckDB and Snowflake copies disagree](../duckdb-retirement-cutover/issues/19-sec-company-ticker-cross-store-divergence.md) (duckdb-retirement-cutover Ticket 19, blocks Ticket 21 and so Ticket 09) — closed 2026-09-14 as explained (operator decision). Snowflake is right: the old canonical DuckDB file kept 512 tickers SEC had dropped, because the publish merge never deleted canonical-only rows; the orphan count is the catalog-vs-captured-companies contract, not missing data. `contracts.py` left unchanged. Ticket 21 is unblocked but still needs its own go-ahead.

- [Apply DuckDB file lifecycle disposition](../duckdb-retirement-cutover/issues/21-apply-duckdb-file-lifecycle-disposition.md) (duckdb-retirement-cutover Ticket 21, blocked Ticket 09) — resolved 2026-09-14 with operator go-ahead. Two 7-day `expiration` lifecycle rules on the exact `silver.duckdb` and `shards/` keys, applied to prod via Terraform (plan: 1 change, 0 destroy; no drift after). The objects are already older than 7 days, so S3 delete-markers them within about a day; each stays restorable as a noncurrent version for 7 days after that. Ticket 09 is now the frontier (Ticket 12's PR #633 merged).

- [Remove `duckdb` and delete the DuckDB engine](issues/09-remove-duckdb-dependency.md) — **split 2026-09-14**, not resolved: too big for one session (35 production importers, 60 test files, 34 live methods). Now Tickets 13–17, expand–contract: schema snapshot (13, frontier) → store-free write path (14) → delete dead readers and tools (15) → two operator decisions on `compute-windows`' reference snapshot and the prod no-op `parse-ownership-bronze` (16, frontier) → engine deletion, `duckdb` out of `pyproject`, deps-image rebuild (17). Ticket 09 closes with 17.

## Not yet specified

- "Equivalent semantics" per table resolved in practice by Tickets 02/03, not as a separate
  design ticket: the contract is the dbt silver model's collapse (`QUALIFY` partition key +
  first-seen/last-seen column split), which must match the table's old `ON CONFLICT` key and
  `DO UPDATE SET` list — Tickets 04–06 check that per table before switching, and only in-process
  readers (none left after 03) needed the semantics reproduced in Python.
- Company-facts retirement against Snowflake silver: `retire_financial_facts_not_in_snapshot`/
  `retire_accounting_flags_not_in_snapshot` were deleted with Tickets 02/03 (they could only
  find rows in local DuckDB, and their sole caller never reached Snowflake anyway). The Ticket
  35 Silver Landing Retirement Record mechanism (`silver_landing_retirement` + the
  `silver_not_retired` dbt macro, already live for the reference catalog) is the natural
  home, but it needs the prior snapshot's membership read from Snowflake silver — not
  specified. Same fog covers wiring `drive_company_facts_discovery.py` to a landing export at
  all (it has none today, so its writes go nowhere). Also the reference catalog
  (`drive-reference-catalog-discovery`, dormant): its read of the earlier ticker list, which
  feeds its retirement records, still queries the empty local store (Ticket 06e left it
  unchanged); it must come from Snowflake silver when the change-propagation map wires the
  driver.
- Live verification of Tickets 02/03: a prod entity-facts run after deploy showing
  `SEC_FINANCIAL_FACT`/`SEC_FINANCIAL_DERIVED`/`SEC_ACCOUNTING_FLAG` landing rows (scores
  populated) — the "done" bar both tickets still owe.
- Silver-landing timestamps load 7–8 hours late, found 2026-09-14 by Ticket 19:
  [duckdb-retirement-cutover Ticket 22](../duckdb-retirement-cutover/issues/22-silver-landing-timestamps-shifted-by-account-timezone.md).
  Platform-wide (every `TIMESTAMP_TZ` in `EDGARTOOLS_SILVER_LANDING`, and `EDGARTOOLS_SOURCE` too),
  not DuckDB-specific; filed there only because Ticket 19 found it. Diagnosed 2026-09-14 (COPY
  INTO labels Parquet UTC times with the session zone). Deployed and corrected in one window
  2026-09-14 19:33–19:46 ET: both loading tasks pinned to UTC, 21,765,149 values relabelled
  (backups in `T22_TIMESTAMP_BACKUP` until 2026-09-21), the three MDM `ingested_at` markers
  relabelled, silver and gold refreshed. Still open: live check on the next real load, then drop
  the clones. Follow-up:
  [Ticket 23](../duckdb-retirement-cutover/issues/23-consolidate-snowflake-run-manifest-task-definitions.md)
  (the manifest task's three definitions).

## Out of scope

- `application/silver_event_reducer.py` + `merge_candidate_into_canonical`'s redesign — the
  decoupled-bronze-pipeline map's Phase 0 reducer merges per-event DuckDB deltas into a
  canonical `silver.duckdb` that DuckDB Retirement Cutover Ticket 10 already retired; it is
  "not wired to any live queue" by its own docstring. Whether Phase 0 is redone against the
  Snowflake landing zone is that map's design question (noted there 2026-09-13). Here it is
  only dead code that leaves with the engine in Ticket 09.
