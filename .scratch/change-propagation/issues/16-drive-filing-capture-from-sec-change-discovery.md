# 16 — Drive filing capture from SEC change discovery

**What to build:** Turn captured SEC change data into a sealed, auditable set
of filing candidates and drive each candidate through ledger-gated acquisition
without manual candidate construction.

**Blocked by:** 15 — Capture one filing-artifact family through the gated Facade

**Status:** resolved

- [x] A captured SEC change observation produces a counted, ordered, digested
  Discovery Manifest for one bounded interval.
- [x] Every in-universe candidate receives exactly one Fetch Decision tied to
  the discovery evidence and registry version.
- [x] The interval cannot complete while any candidate is deferred, failed, or
  otherwise lacks an authorized terminal disposition.
- [x] Replaying the same discovery evidence does not duplicate decisions,
  network requests, or logical source work.
- [x] An end-to-end test proves a newly announced filing reaches verified
  Bronze while an unchanged or excluded candidate performs no download.

## Answer

Delivered as `edgar_warehouse/acquisition/discovery.py` and a new
`drive-filing-discovery-for-date` CLI command
(`edgar_warehouse/application/workflows/drive_filing_discovery.py`),
registered through Ticket 13's handler seam exactly like
`capture-filing-artifact`. Landed on PR #447 (merged `bae5637e`).

Deliberately does not touch the legacy daily-index fetch/bronze path
itself — `load-daily-form-index-for-date`'s own unmodified output
(`stg_daily_index_filing` rows sealed by a `sec_daily_index_checkpoint` row
with `status='succeeded'`) is the discovery evidence this command seals into
a `DiscoveryManifest`: deduplicated by accession, deterministically ordered,
digested (`sha256` over the ordered candidate set). "In-universe" is scoped
to ownership forms (3/3A/4/4A/5/5A — the same family Ticket 15 proved
end-to-end); out-of-scope candidates get an `OUT_OF_SCOPE` Fetch Decision
with no download rather than being silently dropped from the manifest.
"Registry version" (criterion 2) is threaded through the Fetch Decision's
`cause_reference` via a caller-supplied `--registry-version` string — the
full versioned-registry mechanism is explicitly Ticket 20's job, not built
here.

Code review (parallel Standards + Spec `/code-review`) found two real gaps,
both fixed before merge:
1. **Standards**: the new command's manifest-writing helpers were a
   byte-for-byte copy of `capture-filing-artifact`'s — the "sibling path
   silently diverges" shape CLAUDE.md's incident log warns about
   repeatedly. Factored into a shared
   `edgar_warehouse/application/workflows/acquisition_run_writes.py`, used
   by both workflows now (`capture_filing_artifact.py`'s own private
   copies deleted).
2. **Spec**: `drive_discovery_manifest`'s initial `create_fetch_decision`
   call sat outside the per-candidate `try/except`, so a ledger-level
   rejection (e.g. replaying the same interval with a different
   `--registry-version`, which changes the Fetch Decision's
   `cause_reference` and trips `CandidateDecisionConflict`) aborted the
   *entire* drive call instead of leaving just that one candidate
   unsettled — directly contradicting acceptance criterion 3. Fixed by
   widening the per-candidate guard; a rejected candidate now has
   `decision_id`/`fetch_disposition=None` and stays unsettled without
   touching any other candidate in the same call. Regression test:
   `test_conflicting_replay_with_a_different_registry_version_does_not_abort_the_rest_of_the_interval`.

Tests: `tests/acquisition/test_discovery.py` (12 cases — manifest
ordering/dedup/digest determinism/in-scope marking, drive
success/exclusion/replay-safety/partial-failure/conflicting-replay),
`tests/application/test_drive_filing_discovery_command.py` (4 cases —
end-to-end CLI capture proving a newly announced Form 4 reaches verified
Bronze while an excluded 10-K performs zero network calls, replay
idempotency, two fail-closed-on-unsealed-discovery cases). Full repo suite
green: 2399 passed, 4 skipped, only the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures.
