# Retire duplicated engine checks from PostgreSQL integration

Operator, 2026-10-22: keep storage integration tests; retire duplicated engine
tests. Shared programs own calculation. PostgreSQL and MySQL must still prove
durable storage, transactions, constraints, migrations, grants, concurrency,
history, exact transport, indexed reads and recovery through real callers.

- [x] Inspect live ownership and main; create a fresh Codex branch/worktree. Verified 2026-10-23 05:56 ET: live refs and overlap guard; fresh dedicated worktree.
- [x] Inventory PostgreSQL integration cases and identify shared engine/storage coverage before any retirement. Verified 2026-10-23 05:56 ET: 64-module AST inventory and assertion comparison.
- [x] Record an explicit replacement/retention map; retain unique storage and caller checks. Verified 2026-10-23 05:56 ET: replacement and retention map below.
- [x] Establish an affected baseline against the current native implementation. Verified 2026-10-23 05:56 ET: 47 passing baseline cases.
- [x] Move any uncovered calculation cases into database-free engine tests, then retire their duplicated PostgreSQL cases. Verified 2026-10-23 05:56 ET: eight passing database-free cases; native facade unchanged.
- [x] Retire PostgreSQL-only storage checks only where the same contract remains covered on both selected engines. Verified 2026-10-23 05:56 ET: 57 storage cases passed separately on PostgreSQL and MySQL.
- [x] Verify affected engine and storage cases, imports, collection and case-count changes; use bounded test runs. Verified 2026-10-23 05:56 ET: 41 affected cases, 44 final engine cases and 510 integration cases collected.
- [x] Review Standards, Spec and GoF; publish the change and verify CI without removing the storage gate. Verified 2026-10-23 06:07 ET: PR #1145, all nine CI checks green on source head `fffe980e`; no runtime or CI selection change.
- [x] Learning → skill: none; the existing mdm-engineering “Compute once in programs” and “Choose the cheapest proof” rules already cover this boundary. Reviewed 2026-10-23 05:56 ET.

## Audit boundary

Initial AST inventory: 64 integration modules, 464 top-level test functions
(parameterization and class methods are counted separately by pytest). A test
is not a duplicate merely because it calls shared calculation. Normal candidate
retrieval, retained state, stored bytes, migration/permission enforcement,
publication and recovery remain storage contracts. A missing replacement keeps
the original test in place.

The matching modules changed together through #1141, while shared native pair
comparison already has a database-free facade. Keep the existing test seams;
use an explicit behavior matrix rather than a new test framework or mock
database. A database-free calculation test cannot replace a storage assertion.

## Replacement map

Each retired case has a named surviving assertion; no module or CI job is
excluded. The matching engine still runs through its normal Python/native
facade, without a database or a mock replacement for calculation.

| Retired PostgreSQL check | Surviving check |
| --- | --- |
| `test_a_name_the_census_gives_two_leis_waits` | `test_pair_policy_without_storage[ambiguous_candidates]`, both matching rules refuse |
| `test_a_name_another_sec_filer_carried_waits` | `test_pair_policy_without_storage[ambiguous_holders]`, both refuse |
| `test_a_gleif_record_updated_since_the_census_waits` | `test_pair_policy_without_storage[stale_census]`, both refuse; existing effective-time matrix remains |
| `test_a_different_legal_form_waits` | `test_pair_policy_without_storage[different_legal_form]`, both refuse |
| `test_an_inactive_gleif_entity_waits` | `test_pair_policy_without_storage[inactive_candidate]`, both refuse |
| `test_neither_place_agreeing_waits` | `test_pair_policy_without_storage[different_places]`, both refuse |
| `test_the_postcode_rule_vetoes_two_places_of_incorporation` | `test_pair_policy_without_storage[conflicting_jurisdictions]`, both refuse despite equal postcodes |
| `test_the_postcode_rule_sets_aside_a_us_state_both_other_sources_contradict` | `test_pair_policy_without_storage[foreign_business_country]`, jurisdiction refuses, postcode accepts |
| `test_a_cycle_never_publishes` | `tests/reference_storage/test_reference_store.py::test_cycles_and_artifact_failure_publish_nothing`, real PostgreSQL/MySQL approval state and no published paths |
| `test_upsert_changes_only_changed_rows_and_snapshot_removes_rows_no_longer_delivered` | `tests/silver_storage/test_delivery.py::test_normal_modes_repeat_and_populated_migration`, real PostgreSQL/MySQL counts, exact retained rows, timestamps, snapshot deletion and empty refusal |
| `test_a_bad_delivery_writes_nothing` (four cases) | `tests/silver_storage/test_delivery.py::test_bad_delivery_is_atomic`, same bad date, null key, duplicate key and nested scalar; real PostgreSQL/MySQL empty destination |

## Retained contracts

- All six remaining matching integration cases: retrieval in either arrival
  order, same-batch identity, inactive rule, held identifier and conflict review.
- RDM imports, CLI, metadata, lifecycle, historical paths, raw SQL constraints,
  grants and PostgreSQL search edge cases. Shared cycle rollback coverage runs
  on both selected databases, rather than disappearing with the old case.
- Silver real MDM resolution and later refresh, redirects after merge, quality,
  registration metadata/comments/rights, quoting and legacy interval transport.
  Callback-based identifier tests do not replace the real MDM lookup path.
- Every other integration module remains. A policy outcome embedded in a
  durable-state, caller, recovery or concurrency assertion is not declared
  redundant merely because the shared engine also calculates it.
- Existing adapter tests and all CI groups remain, including SQL Server's
  existing checks. This ticket does not qualify the normal MySQL MDM caller.

## Verification record

- Pre-change baseline: 47 cases passed in 26.83 seconds on main at #1141.
- Main advanced while work paused: #1142, #1143 and #1144 merged. Rebased onto
  `8c97af69` before changing tests; native wheel rebuilt for its current ABI.
- Measured affected-case change: retire 14 PostgreSQL cases across 11 functions; add eight
  database-free matching cases. Strengthen existing shared storage assertions
  without adding storage cases. Test count is not a runtime benchmark.

- After: 41 affected cases passed in 25.48 seconds; final engine/profile run
  passed 44 cases in 6.52 seconds after adding a positive control to every
  moved calculation case. Both rules must accept the invented pair before
  the changed condition is allowed to prove refusal.
- Shared storage: 57 cases passed on PostgreSQL in 19.64 seconds and 57 on
  MySQL in 24.86 seconds, each using isolated databases and restricted roles.
- All integration modules collect successfully: 510 parameterized cases.
  No fixtures, imports, markers or CI selection were removed.
- Every local invocation stayed below five minutes. Timing here records
  outcomes, not a controlled before/after performance claim.

## Standards

Dedicated branch/worktree, explicit replacement map, invented new examples,
private logs and per-worktree testmon data. Storage suites use real servers,
isolated databases and restricted principals; no skip or mocked persistence.
No runtime code, migration, deployment or CI gate changes.

## Spec

Retire only demonstrated duplication. The eight moved calculation cases each
exercise both rules through shared native computation. Six PostgreSQL-only
storage cases now rely on the existing stronger two-engine matrix, with the
missing timestamp, inserted-count, retained-key and cycle-path assertions
made explicit. Candidate retrieval, real MDM identifier reads, durable held
identifiers, conflict state, migrations, grants, concurrency and recovery
stay in integration coverage. Broader MDM portability remains separate work.

## GoF

Reviewed matching co-change through #1141/#1142 and shared storage tests from
#1121. Keep the current native facade and storage adapter seams. The test
matrix removes duplicated calculation setup; no new hierarchy or design
pattern has an evidence-backed benefit for this change.

- Full CI verified 2026-10-23 06:07 ET: all nine checks passed on `fffe980e`, run
  [39935597121](https://github.com/paulananth/edgartools-platform/actions/runs/39935597121).
  PostgreSQL integration took 9 minutes 14 seconds; no speedup claim.
  The completion-record commit changes only this ticket; final-head CI remains
  the PR readiness gate.
