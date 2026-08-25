# 24 — Migrate ADV sources

**What to build:** Carry ADV filing and bulk-source changes through explicit
source identity and completeness policies into verified adviser, office,
disclosure, fund, and roster Silver outcomes.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** resolved (partially — see Answer for the one bullet that depends
on a later ticket)

- [x] The ADV Strategy distinguishes filing or accession identity from complete
  bulk-dataset identity and declares the proper scopes for each.
- [x] Rolling-window absence cannot retire evidence outside a proved complete
  archive, filing, or roster scope.
- [x] Complete, incomplete, unchanged, superseding, replayed, and valid-empty
  inputs produce explicit verified outcomes.
- [~] ADV parsing remains outside the acquisition Facade and cannot begin until
  its exact Bronze evidence is verified and ledger-bound.
- [x] ADV acquisition uses bundled Command registration without introducing a
  Template Method superclass for merely similar family workflows.

## Answer

**Two Strategies, not three, and not one shared superclass.** ADV's real
identity split is bulk-dataset-snapshot vs. accession — not per-source-kind:

- `adv_bulk_dataset` (`AdvBulkDatasetPolicy`, `source_family_registry.py`):
  one Strategy covers both IAPD ADV bulk archives (`iapd_adv_bulk`) and IAPD
  Firm Roster archives (`iapd_firm_roster`, two disjoint-by-CRD variants —
  registered/exempt — per period) — both are complete-snapshot-per-
  `dataset_period`, identical fetch/completeness mechanics
  (`sec_client.download_sec_bytes`, non-empty-payload), same shape as
  Ticket 23's `reference_catalog` fixed-source-name-set family. New modules:
  `acquisition/adv_bulk_dataset_discovery.py` (candidate resolution +
  ledger-gated capture) and `acquisition/adv_bulk_dataset_silver_acceptance.py`
  (Silver write/verify), plus the `drive-adv-bulk-dataset-discovery` workflow/
  command/CLI/registry wiring, mirroring `reference_catalog`'s four-file shape
  exactly.
- `adv_filing` (accession identity): reuses `FilingArtifactPolicy` verbatim
  under a distinct family name/coverage row (own `in_scope_forms` = the 9 ADV
  form variants) — Strategy reuse across families, not a Template Method
  superclass; see `source_family_registry.py`'s own reuse note.

**Resolving "which archive to fetch" is a discovery input, not a Fetch
Decision.** SEC/IAPD's `reports_metadata.json` and the Firm Roster HTML
listing must be read to know *which* concrete archive URL to fetch — reused
`adv_bulk_fetch.py`/`firm_roster_fetch.py`'s own
`rolling_window_periods`/`periods_to_fetch`/`select_downloadable` and
`latest_available_period`/`period_to_fetch`/`select_downloadable_variants`
unmodified (not reimplemented) rather than inventing new resolution logic —
same discipline Ticket 23 used for `_parse_company_ticker_rows`. Only the
resulting concrete archive download is ledger-gated. `already_ingested` is
always passed as an empty set: replay-safety comes entirely from
`create_fetch_decision`'s idempotent CAPTURED short-circuit (same as every
sibling family), not a pre-filter — so the manifest always covers the full
rolling window / latest period, and a period the metadata/listing doesn't
(yet) publish lands in `unpublished_periods`, not an error (bullet 3's valid-
empty contract; verified live: a period the metadata omits produces zero
candidates for that period, not a failure).

**Bullet 2 (rolling-window absence)** is satisfied structurally: nothing in
this family's manifest-building or Silver-acceptance path ever deletes or
retires a prior period's evidence when it rolls out of the trailing window —
the window only bounds what gets *newly proposed*, and each period's own
Logical Source Revision / expected-producer scope
(`adv-bulk-archive/{period}/...`, `adv-firm-roster/{variant}/{period}/...`)
is permanent once materialized.

**Silver-write reuse, same posture as Tickets 22/23:** `adv_bulk_dataset_
silver_acceptance.py` calls `adv_bulk_ingest.ingest_adv_bulk_archive`/
`adv_firm_roster_ingest.ingest_firm_roster_archive` unmodified — in
particular this does NOT reimplement `ingest_adv_bulk_archive`'s per-
accession `fund_index` scoping (the real SMALLINT-overflow fix documented in
CLAUDE.md's Schema-conventions section), since calling the existing function
unchanged is what preserves it. Verification is parse-count-vs-write-count
reconciliation (the ingest functions report only counts, not written keys) —
a mismatch is exactly the failure mode this exists to catch (a merge
silently dropping rows), without re-deriving a business-key mapping that
could drift from what the writer actually does (the class of bug Ticket 23's
Standards review caught for the blank-ticker case).

**Bullet 4 — resolved for `adv_bulk_dataset`, honestly partial for
`adv_filing`'s per-accession parsing path.** `AdvBulkDatasetPolicy`'s Bronze
capture is now fully ledger-gated end-to-end (verified live via a real
command-level integration test:
`test_drive_adv_bulk_dataset_discovery_command.py`). The `adv_filing` family
declares accession identity's own scope (bullet 1), but no
`drive-adv-filing-discovery-for-date` command exists yet to actually drive
capture through it — `drive_filing_discovery.py` (the real, working
`daily_index_driven` implementation) is hardcoded to
`FILING_ARTIFACT_SOURCE_FAMILY` only, not parameterized per family. ADV
filing documents are therefore still captured via the pre-Ticket-14 legacy
path `_run_parse_adv_bronze` reads from (`discover_adv_bronze_artifacts` →
`sec_company_filing`/`sec_filing_attachment`/`sec_raw_object`, confirmed live
by reading that module directly) — `_run_parse_adv_bronze` itself was **not**
modified to gate on a materialized `SourceRevisionRecord` existing for each
accession, since without a driver to ever populate one for the `adv_filing`
family, adding that gate now would make ADV parsing permanently refuse to
run rather than genuinely enforce ledger-boundedness. Closing this requires
either generalizing `drive_filing_discovery.py` to take a `source_family`
parameter (reuse) or a new sibling driver (duplication, consistent with
bullet 5) — a real, scoped follow-up, not silently carried forward as done.
Confirmed the collision risk an earlier design pass flagged (bulk-archive
rows sharing `sec_adv_filing`'s single-column `accession_number` PK with
real EDGAR accessions) does **not** exist: bulk rows are keyed
`iapd-adv:{filing_id}`, structurally distinct from EDGAR's
`NNNNNNNNNN-YY-NNNNNN` accession shape, verified by reading
`adv_bulk_ingest.py` directly — no defensive keying needed.

**Tests:** 12 new (7 `test_adv_bulk_dataset_discovery.py`, 4
`test_adv_bulk_dataset_silver_acceptance.py`, 1 command-level integration
test), all passed on first implementation (no bug-fix cycle this ticket, per
the prior three tickets' hard-won lessons applied preemptively: source-name/
kind-only candidate IDs, upfront `UnsupportedRequiredProducers` gate,
`dataset_path_catalog.py` wiring remembered proactively). `tests/acquisition/`
+ `tests/application/` (593 tests) and `tests/architecture/` (534 tests,
confirming the new `sec_client` import into `source_family_registry.py` is a
permitted per-source-module boundary, not a `warehouse_orchestrator.py`
violation) both green.
