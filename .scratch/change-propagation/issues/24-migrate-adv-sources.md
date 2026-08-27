# 24 — Migrate ADV sources

**What to build:** Carry ADV filing and bulk-source changes through explicit
source identity and completeness policies into verified adviser, office,
disclosure, fund, and roster Silver outcomes.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** resolved

- [x] The ADV Strategy distinguishes filing or accession identity from complete
  bulk-dataset identity and declares the proper scopes for each.
- [x] Rolling-window absence cannot retire evidence outside a proved complete
  archive, filing, or roster scope.
- [x] Complete, incomplete, unchanged, superseding, replayed, and valid-empty
  inputs produce explicit verified outcomes.
- [x] ADV parsing remains outside the acquisition Facade and cannot begin until
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

**Bullet 4 — resolved for both `adv_bulk_dataset` and `adv_filing`.**
`AdvBulkDatasetPolicy`'s Bronze capture is fully ledger-gated end-to-end
(verified live via a real command-level integration test:
`test_drive_adv_bulk_dataset_discovery_command.py`). The `adv_filing`
family's own gap — no driver existed to actually drive capture through its
already-declared coverage row — is now closed: `drive_filing_discovery.py`'s
`run_drive_filing_discovery_for_date` was generalized into a shared
`_run_daily_index_driven_discovery(args, *, source_family, command_name,
default_registry_version, default_required_producer)` body, parameterized
by family/command name rather than hardcoded to `FILING_ARTIFACT_SOURCE_FAMILY`
(reuse, the option this ticket's own text named as preferred — the mechanism
was already fully generic one layer down in `discovery.py`/
`silver_acceptance.py`, which already took `source_family`/
`required_producers` as parameters; only this workflow function itself was
hardcoded). `run_drive_adv_filing_discovery_for_date` is the new thin
wrapper, registered as `drive-adv-filing-discovery-for-date`
(`acquisition_command_registry.py`, `cli.py`, `dataset_path_catalog.py`'s
shared manifest-path bucket). ADV filing documents can now flow through this
real, ledger-gated driver as an available path.

**Correction (caught by `/code-review`'s Spec pass, not overclaimed as a
clean replacement):** this driver does **not** retire either pre-existing
legacy path for ADV, and this ticket's first draft wording ("instead of...
going forward") overstated that. Two separate legacy mechanisms remain
untouched: `_run_parse_adv_bronze`/`discover_adv_bronze_artifacts`
(downstream business-data parsing off already-captured Bronze — correctly
scoped out of this ticket already, per bullet 4's own text), and, newly
surfaced by review, `warehouse_orchestrator.py`'s standard artifact-fetch
pipeline (`fetch_filing_artifacts`, gated by `_is_configured_parser_form`,
which still lists `ADV_FORMS` unmodified) — the same `bootstrap-next`/
`load_history` path that independently captures ADV documents into the
identical `sec_raw_object`/`sec_filing_attachment` tables, entirely outside
the ledger. Verified this is **not a new gap this ticket introduced**: the
identical overlap already exists for `filing_artifact`'s own ownership forms
(`OWNERSHIP_FORMS`, same function, never removed by Tickets 16/17/29) and
was never disclosed in those tickets' own Answer sections either — this new
`adv_filing` driver is scoped exactly the same way its `filing_artifact`
sibling was: it adds the new ledger-gated path, it does not retire the old
one. Retiring either legacy artifact-fetch path for any family is
explicitly [Ticket 27](27-contract-legacy-acquisition-bypasses.md)'s job
("Remove bypasses only after every source family proves the authoritative
path"), already tracked, not a new follow-up this correction needs to spawn.

**A second, genuine bug found and fixed while wiring the new driver, not
anticipated by this ticket's own bullet-4 writeup:**
`discovery.discovery_candidate_id(business_date, accession_number)` keyed
Fetch-Decision identity on interval + accession only, with no
`source_family` component — accidentally globally unique so long as exactly
one family ever drove daily-index discovery. Running the new `drive-adv-filing-discovery-for-date` against the exact same
sealed daily index `drive-filing-discovery-for-date` also reads reproduced
this live: the same business_date + accession pair is a genuine
candidate in *both* families' manifests (in-scope for one, excluded for the
other), and `AcquisitionLedger.create_fetch_decision`'s `candidate_id`
uniqueness check is global, not scoped by `source_family` — so the second
family's driver failed outright with "already has a different Source Fetch
Decision." Fixed by adding an optional `source_family` keyword to
`discovery_candidate_id`, **deliberately preserving `filing_artifact`'s
exact legacy id format unchanged** (no family segment) rather than adding it
uniformly: Ticket 29 already ran a real prod dry run that wrote live ledger
rows under the old format, and that id is exactly what lets a replay
recognize an already-CAPTURED candidate without a real SEC fetch (this
repo's "SEC data idempotency" policy) — uniformly changing the format would
have silently broken that recognition on the very next prod replay for an
already-processed date, causing a real re-fetch from SEC. Every other family
(including the new `adv_filing`) gets the family segment, since none of them
has live ledger history whose format needs preserving. Locked in by two new
tests in `tests/acquisition/test_discovery.py`: one pinning
`filing_artifact`'s exact legacy string, one proving `adv_filing` produces a
distinct id for the same interval/accession.

Confirmed the collision risk an earlier design pass flagged (bulk-archive
rows sharing `sec_adv_filing`'s single-column `accession_number` PK with
real EDGAR accessions) does **not** exist: bulk rows are keyed
`iapd-adv:{filing_id}`, structurally distinct from EDGAR's
`NNNNNNNNNN-YY-NNNNNN` accession shape, verified by reading
`adv_bulk_ingest.py` directly — no defensive keying needed.

**Tests (bullet 4 follow-up):** new
`tests/application/test_drive_adv_filing_discovery_command.py` (4 tests) —
capture + exclusion, no-op replay, fail-closed on unsealed discovery, and
the real proof this gap needed: both families' drivers running against the
exact same sealed daily-index observation, each only ever touching its own
in-scope forms, with no ledger collision. Plus the two `discovery_candidate_id`
regression tests above.

**Tests:** 13 new (7 `test_adv_bulk_dataset_discovery.py`, 5
`test_adv_bulk_dataset_silver_acceptance.py`, 1 command-level integration
test), all passed on first implementation (no bug-fix cycle this ticket, per
the prior three tickets' hard-won lessons applied preemptively: source-name/
kind-only candidate IDs, upfront `UnsupportedRequiredProducers` gate,
`dataset_path_catalog.py` wiring remembered proactively). `tests/acquisition/`
+ `tests/application/` (593+ tests) and `tests/architecture/` (534 tests,
confirming the new `sec_client` import into `source_family_registry.py` is a
permitted per-source-module boundary, not a `warehouse_orchestrator.py`
violation) both green. Full repo suite green: 2592 passed, 4 skipped.

**`/code-review` (Standards + Spec, two parallel agents against `origin/main`):**
Standards found no hard violations — two minor, disclosed judgement calls
(a `source_kind` dispatch branch in the silver-acceptance module, and a
duplicated family-name-string constant between the discovery module and
`source_family_registry.py`), both either justified by ADV's real data shape
or faithfully inherited from Ticket 23's own precedent, not new smells.
Spec confirmed bullets 1/4/5 as accurately implemented/reported, and no
scope creep — but caught one real gap: bullet 3 ("...superseding...replayed...
produce explicit verified outcomes") was checked `[x]` without a test
actually exercising the *superseding* case (a second, content-different
capture for the same `dataset_period`/`logical_source_key`, proving
`ContentImpact.CHANGED` — not `NO_IMPACT` — and a correct Silver upsert of
the new content). Confirmed via the reviewer's own repo-wide grep that this
gap is pre-existing across Tickets 21-23 too (not a new regression), but
fixed for this family anyway since it was cheap and the failure mode is
real: `test_a_content_different_capture_for_the_same_period_supersedes_and_
settles_verified` now proves a same-`FilingID` archive republished with a
corrected field value produces a genuinely re-verified decision (non-empty
`expected_producers`, not the empty-tuple `NO_IMPACT` shape) and that
Silver's `accession_number`-keyed upsert reflects the corrected value with
no duplicate row. Bullet 3 is now `[x]` honestly for this family; the same
gap for Tickets 21-23 is not retroactively fixed here (out of this ticket's
scope) and remains open for whoever picks it up.
