# Complete and Close Verified Per-Load Quality Evidence (#1434)

Type: task
Status: resolved
Blocked by: none
Blocks: none
Labels: wayfinder:task

## Question

Does the fresh implementation PR pass every acceptance gate in [Preserve
verified per-load silver quality evidence (#1434)](https://github.com/paulananth/edgartools-platform/issues/1434)
on current `main`, and is the evidence sufficient to close the goal?

## Checklist

- [x] Confirm the implementation PR includes final race, receipt, retry,
  concurrency, precision, failure-action, history and readback evidence.
  Every kind has evidence on current `main` (2026-11-10 01:30 ET):

  | Kind | Where |
  | --- | --- |
  | Receipt | `edgar_warehouse/workers/silver_land.py:175-194` writes the version-2 receipt; `tests/unit/test_silver_land_quality.py:85` |
  | Old discarded-report behavior | `tests/unit/test_silver_land_quality.py:85` — the test requires the real report in the receipt, so it fails against the old behavior the issue describes |
  | Race | `tests/integration/test_configured_bookkeeping_postgres.py:1044` — a superseded attempt is refused atomically, with and without a completed replacement |
  | Retry | `tests/unit/test_silver_land_quality.py:127` — a re-executed unit writes the same receipt bytes; `:142` — another unit's retained receipt is never reused |
  | Concurrency | `tests/silver_storage/test_delivery.py:178` — concurrent deliveries serialize and replay; the worker never writes the shared file (`silver_land.py:183`, `record_quality_results=False`) |
  | Precision | `tests/unit/test_bookkeeping_quality.py` — a count that is not an exact integer is refused, the widest signed 64-bit count survives whole, and a sum that would overflow is refused (added by this closeout) |
  | Failure action | `tests/unit/test_silver_land_quality.py:85` — flag and exception outcomes are both retained with their counts |
  | History | `tests/unit/test_bookkeeping_quality.py:108` — per-unit correlation and unique timestamps; `tests/unit/test_rules_catalog.py:976` — every run result is preserved and verified, and a replay is idempotent |
  | Readback | `tests/unit/test_rules_catalog.py:937, 997, 1014` — the result is read back at its exact timestamp, one mismatching result is corrected once, and a second correction stops |

- [x] Confirm recovery prerequisites and the operator UI observation are
  recorded. The recovery owner, procedure, measurement and the operator's
  5-minute maximum are in `skills/bookkeeping/RECOVERY.md` under "The
  version-2 quality receipt: owner, procedure, measurement"; the measured
  resume was 0.146 s to 0.263 s over nine runs in
  `tests/integration/test_quality_recovery_postgres.py`. The operator's UI
  observation is recorded in
  [Observe Per-Load History in the Shipped OpenMetadata UI](06-observe-history-in-shipped-openmetadata-ui.md)
  (2026-11-10 01:30 ET).

- [x] Require green CI on the exact current head and merge the ready PR. The
  implementation PRs are merged: #1484 (restore verified per-load quality
  results), #1499 (atomic quality attempt supersession), #1582 (make the
  version-2 receipt resumable and prove the recovery). The end-to-end proof
  (#1588) and the UI observation (#1599) are merged with all twelve CI checks
  green on their exact heads (2026-11-10 01:30 ET).

- [x] Recheck [Preserve verified per-load silver quality evidence]'s acceptance
  criteria against the merged behavior.

  | Required result | Verdict | Evidence |
  | --- | --- | --- |
  | Preserve quality evidence per run, step and work unit in an immutable candidate receipt, with a versioned contract and compatibility for existing receipts and pinned runtimes | met | `silver_land.py:68` (`_receipt`), `:78` (`_quality_identity`), `:97` (`_quality_observation`), `:173-194` (the worker writes the receipt); `silver_land.py:242` verifies a version-1 receipt unchanged; `tests/unit/test_silver_land_quality.py:159`; a pinned worker runtime is refused when it changes (`tests/integration/test_configured_bookkeeping_postgres.py:863`) |
  | Retain executed check identity, rows checked/failed, failure action and observation time; counts only, no source records or credentials | met | `silver_land.py:97` (`_quality_observation`) records the run, step, an opaque 24-character work-unit reference, the check id, kind, failure action, observation time and counts — never the unit key or the attempt (`tests/unit/test_silver_land_quality.py:93-94`); the work-unit reference is a digest precisely so no provider identifier is copied (`silver_land.py:91`) |
  | Have the verifier recompute/admit that evidence; account for flag and exception outcomes | met | `silver_land.py:142` (`_recomputed_quality`) and `silver_land.py:218` (`verify`) recompute from the original rows and reject altered evidence (`tests/unit/test_silver_land_quality.py:105`); `edgar_warehouse/bookkeeping/clean/quality.py:32` (`aggregate`) admits only verified receipts and keeps the failure action |
  | Aggregate verified units without double-counting retries or overwriting concurrent units through a shared latest-results file | met | `silver_land.py:183` never writes the shared `QUALITY_RESULTS_FILE`; the receipt names the work unit, not the attempt, so a retry reuses the observation time (`silver_land.py:119`); `quality.py:32` walks expected units, so a retry is one unit; `tests/silver_storage/test_delivery.py:178`; `tests/integration/test_configured_bookkeeping_postgres.py:1044` |
  | Publish genuine corresponding native quality results and verify readback; keep absent or incomplete evidence visibly unknown | met | `quality.py:114` (`catalog_results`) and `edgar_warehouse/rules/catalog.py:1140-1237`; `tests/unit/test_bookkeeping_quality.py:79` keeps an incomplete run's units unknown; a publish of unknown evidence is refused and changes nothing, verified live against the local OpenMetadata |
  | Add a test that fails on the current discarded-report behavior, plus retry, concurrency, precision, flag/exception and historical receipt tests | met | Discarded-report: `tests/unit/test_silver_land_quality.py:85`. Retry: `:127`, `:142`. Concurrency: `tests/silver_storage/test_delivery.py:178`. Precision: `tests/unit/test_bookkeeping_quality.py` (exact integer, the widest signed 64-bit count, and aggregate overflow). Flag/exception: `tests/unit/test_silver_land_quality.py:85`. Historical receipt: `:159` and `silver_land.py:242` |

- [x] Close [Preserve verified per-load silver quality evidence] only when every
  requirement is verified; otherwise keep it open and name the remaining
  blocker. Every requirement is verified, so issue #1434 is closed. The one
  gap this closeout found — the issue asks for a precision test and only the
  rejection of an over-range count was covered — is closed by the tests added
  here, each proved to fail against a mutated guard (2026-11-10 01:30 ET).

- [x] Learning → skill: `none` beyond the reference-file learning in ticket
  06. The precision rule the tests now pin is the repository's standing rule
  (an integer is a `BIGINT`; a count is an exact signed 64-bit value), already
  written in `AGENTS.md`; no skill line changed (2026-11-10 01:30 ET).

## Answer

Yes. Every acceptance gate in issue #1434 is met on current `main`, and the
evidence is sufficient to close it.

The behavior was proved end to end against a real local OpenMetadata, not only
in tests: three complete loads of an already-captured Form 13F delivery each
produced admitted version-2 evidence, were published per load, and were
confirmed by exact timestamped readback. The case holds three results, each
naming its own Bookkeeping run. A replay published nothing new, `check` was
read-only, and a publish for a run without complete evidence was refused and
left the published history unchanged.

The shipped UI shows the newest result's full load reference and renders
history as a chart with no per-point tooltip and no result list, so an older
load's result text is read through the API. Confirmed, failed and never-run
are distinguishable, and a pending or incomplete load cannot be presented as
confirmed publication: the result status vocabulary is Success, Failed and
Aborted only.

The feature stays disabled in production. `SILVER_QUALITY_EVIDENCE_V2` is
unset, and registering the check in a production source's rules and setting
the gate in the shared environment is the operator's enablement decision, which
has not been made. Closing the issue records that the mechanism works and is
verified; it does not switch it on.

## The gap this closeout found and closed

Issue #1434 asks for a precision test. The merged code rejected a count that
was not an exact integer and refused a count above the signed 64-bit maximum,
but the tests covered only the rejection of an over-range count. The widest
count a signed 64-bit column holds, a count that arrived as a float, and a
sum that would overflow the column were all unproven.

Three tests were added to `tests/unit/test_bookkeeping_quality.py`, and each
was proved to fail against a mutated guard:

| Mutated guard | Test that caught it |
| --- | --- |
| the exact-integer type check in `catalog_results` | `test_catalog_results_refuse_a_count_that_is_not_an_exact_integer` (whole float, fraction, bool) |
| the signed 64-bit ceiling in `catalog_results` | `test_catalog_results_refuse_unknown_or_unsafe_counts` |
| the aggregate overflow guard | `test_aggregation_refuses_a_sum_that_would_overflow_signed_64_bit_storage` |

`test_catalog_results_keep_the_largest_signed_64_bit_count_exact` pins the
positive boundary: `2**63 - 1` survives whole and stays an `int`.

## Remaining

- [ ] ~~Enable version-2 quality evidence in production rules.~~ Not this
  ticket's to close: the mechanism is verified and the switch-on is the
  operator's decision. The opt-in stays unset.

[Preserve verified per-load silver quality evidence]: https://github.com/paulananth/edgartools-platform/issues/1434
