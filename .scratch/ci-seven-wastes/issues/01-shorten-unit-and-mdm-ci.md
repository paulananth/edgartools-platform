# Shorten Unit and MDM CI without reducing behavior coverage

Type: task
Status: resolved

## Scope

Operator: create a fresh branch, investigate the slow Unit and MDM CI job and
optimize using the seven wastes. Preserve the full test inventory and required
database acceptance. New test scenarios require operator approval before code.

## Parts

- [x] Measure recent successful CI runs, separating startup, build and execution (2026-11-20 14:52 ET): three successful runs below.
- [x] Profile the existing affected code and identify the root cause (2026-11-20 14:52 ET): cProfile counts below; per-test CI durations enabled.
- [x] Review the relevant code and change history using the GoF method (2026-11-20 14:52 ET): repeated work within existing functions; share computed inputs, no pattern abstraction warranted.
- [x] Apply the measured optimization; preserve behavior coverage (2026-11-20 15:01 ET): share operation-local source documents, field winners and service digest; no test changes.
- [x] Verify all affected test files locally (2026-11-20 15:01 ET): 116 passed in 51.02s using testmon with selection disabled on final code.
- [x] Compare complete CI execution and job times against the baseline (2026-11-20 15:01 ET): run 44806172228 passed all 12 jobs; 2,989 passed / one skipped in 231.38s.
- [x] Review Standards, Spec and GoF; publish a PR with evidence (2026-11-20 15:01 ET): three independent reviews, no actionable findings; PR #1957.
- [x] Learning → skill (2026-11-20 15:01 ET): none; the data-platform seven-wastes rule already requires measured cheap proof and carrying computed inputs forward.

## Baseline

At base e8df6ebd3, run 44800864333 executes 2,989 passed, one skipped in
398.83 seconds; dependency installation takes 47 seconds. Runs 44797779761
and 44792230764 spend 538 and 563 seconds in the test step, with 69 and
77 seconds installing dependencies. Runner startup is seconds, not minutes.

## Investigation

Ranked hypotheses: repeated profiling work; oversized fixtures; process startup;
uncached Rust builds. Measure individual test durations before choosing a fix.

## Seven wastes

| Waste | Evidence and action |
|---|---|
| Transport | Mapping generation reads 3,210 documents; pass the already loaded source documents to its readers (170 reads after). |
| Inventory | No cache, extra CI jobs, installed environment, or test server added. Keep one task branch and publish its PR. |
| Motion | CI reports its 30 slowest test phases, so future investigations start with timings. |
| Waiting | Unit/MDM is the measured critical path. Remove repeated computation before adding runners or splitting jobs. |
| Over-processing | Mapping generation recomputes field winners 20 times. Catalog planning expands the same sources five times and hashes the rules tree per service. Compute each once within its operation. |
| Over-production | Preserve the full existing test inventory; add no redundant tests or speculative scheduling framework. |
| Defects | Inputs are local to one operation; the next call rereads disk. Existing tests cover changed rules, independent roots, malformed metadata, publication and workbook edits. |

## Component measurements

Same checkout and environment, cProfile around one operation (these are profiled
component times, not end-to-end CI claims):

| Operation | Before | After | Reads before / after |
|---|---:|---:|---:|
| Mapping Documents | 7.200s | 0.508s | 3,210 / 170 |
| Catalog plan | 2.318s | 0.503s | 816 / 208 |

Each source is expanded once per operation. The field-winner calculation is
shared with every source sheet. Catalog services share their rules digest.
Each call still reads current rules; nothing persists across calls.

The initial broad local unit profiling attempt reached its 280-second deadline
without completing. It reported setup errors before its deadline; it is not
passing validation. All its process-group children were stopped. Validation is
restricted to the affected files, with the complete inventory verified in CI.
No shared data server or other agent's work was changed.

## Local verification

Final implementation head `5ba006ac61a232407f4d9898d67fbf601548a809`:

```bash
TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run --no-sync pytest \
  --testmon --testmon-noselect tests/unit/test_rules_catalog.py \
  tests/unit/test_rules_catalog_coverage.py tests/unit/test_rules_mapdoc.py \
  tests/unit/test_custom_parsing_mapping.py --durations=15 -q --tb=short
```

116 passed in 51.02 seconds. Existing tests verify a changed source changes
its catalog and digest, independent rules roots, workbook round trips and
edits, pipeline discovery/metadata validation, quality publication/readback,
and nested custom parsing. No new tests were added and none were removed.

## Standards

No actionable findings. Configuration stays generic and operation-local;
required CI inventory and validation remain unchanged.

## Spec

No actionable findings. A fresh branch, measured critical path, seven-waste
audit and targeted optimization meet the operator's request; full CI comparison
is recorded below.

## GoF

No pattern refactor warranted. Existing modules own the right responsibilities;
passing already computed inputs removes repeated work without a persistent cache.

## Full CI comparison

Implementation head `5ba006ac61a232407f4d9898d67fbf601548a809`,
[run 44806172228](https://github.com/paulananth/edgartools-platform/actions/runs/44806172228):
all 12 jobs passed, including every required database engine and the aggregate gate.

| Measurement | Main baseline 44800864333 | Implementation 44806172228 |
|---|---:|---:|
| Unit/architecture/MDM test execution | 398.83s | 231.38s |
| Unit/MDM dependency step | 47s | 68s |
| Complete Unit/MDM job | 455s | 309s |
| Complete workflow, including scheduling | 465s | 339s |
| Test result | 2,989 passed / one skipped | 2,989 passed / one skipped |

Test execution improved 42%; the complete Unit/MDM job improved 32%. Install
cost varied and was higher on the optimized run. These are observations from
separate hosted runners, not a controlled hardware benchmark; the component
profiles and read counts isolate the eliminated work.

## Remaining observed work

The new CI duration report identifies two existing load-chain tests at 18.63s
and 18.36s. Each calls its `targets()` helper (which reads all source rules)
inside a loop over chain steps. Hoisting that setup before the loop preserves
all assertions. Operator approval of that existing scenario has been requested
before editing test code, as required by the testing discipline. This observation
is separate from the verified catalog/mapping improvement above.
