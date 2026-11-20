# Shorten Unit and MDM CI without reducing behavior coverage

Type: task
Status: claimed

## Scope

Operator: create a fresh branch, investigate the slow Unit and MDM CI job and
optimize using the seven wastes. Preserve the full test inventory and required
database acceptance. New test scenarios require operator approval before code.

## Parts

- [x] Measure recent successful CI runs, separating startup, build and execution (2026-11-20 14:52 ET): three successful runs below.
- [x] Profile the existing affected code and identify the root cause (2026-11-20 14:52 ET): cProfile counts below; per-test CI durations enabled.
- [x] Review the relevant code and change history using the GoF method (2026-11-20 14:52 ET): repeated work within existing functions; share computed inputs, no pattern abstraction warranted.
- [ ] Apply the smallest measured optimization; preserve behavior coverage.
- [ ] Verify locally within five minutes per invocation and compare CI results.
- [ ] Review Standards, Spec and GoF; publish a PR with evidence.
- [ ] Learning → skill: none identified yet.

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
