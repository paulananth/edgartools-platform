# Shorten Unit and MDM CI without reducing behavior coverage

Type: task
Status: claimed

## Scope

Operator: create a fresh branch, investigate the slow Unit and MDM CI job and
optimize using the seven wastes. Preserve runtime behavior coverage and required
database acceptance. The operator also requested removal of the two slow static
load-chain configuration cross-checks. New test scenarios require operator approval before code.

## Parts

- [x] Measure recent successful CI runs, separating startup, build and execution (2026-11-20 14:52 ET): three successful runs below.
- [x] Profile the existing affected code and identify the root cause (2026-11-20 14:52 ET): cProfile counts below; per-test CI durations enabled.
- [x] Review the relevant code and change history using the GoF method (2026-11-20 14:52 ET): repeated work within existing functions; share computed inputs, no pattern abstraction warranted.
- [x] Apply the measured optimization; preserve behavior coverage (2026-11-20 15:01 ET): share operation-local source documents, field winners and service digest; approved test retirement is recorded below.
- [x] Verify all affected test files locally (2026-11-20 15:01 ET): 116 passed in 51.02s using testmon with selection disabled on final code.
- [x] Compare complete CI execution and job times against the baseline (2026-11-20 15:01 ET): run 44806172228 passed all 12 jobs; 2,989 passed / one skipped in 231.38s.
- [x] Review Standards, Spec and GoF; publish a PR with evidence (2026-11-20 15:01 ET): three independent reviews, no actionable findings; PR #1957.
- [ ] Remove the two requested static cross-checks, verify their surviving runtime guards, and rerun full CI.
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
| Over-production | Keep runtime behavior tests; remove only the two static configuration cross-checks the operator identified; add no speculative scheduling framework. |
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
and nested custom parsing. No new tests were added. Two static chain cross-checks are removed below at the operator's request; these 116 catalog/mapping cases are unchanged.

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

## Requested test removal

The operator explicitly requested removal of these two static configuration
cross-checks after their 18.63s and 18.36s CI costs were reported:

- `test_each_step_gives_exactly_the_facts_its_target_declares_and_the_capture_does_not_state`
- `test_no_step_types_the_date_or_the_order_of_a_delivery_its_capture_states`

Both read the configured chain and compare it with target declarations; neither
runs the load command. Read before deletion: both test bodies; `targets()`;
`load_chain.arguments()` and `plan()`; `Loader.delivery()`;
`target_manifest.write_manifest()`; Bookkeeping `run_inputs()`; and the surviving
runtime tests below. No production code or shared helper is retired.

These are not exact duplicates. Their unique protection is early detection of
mistakes in the checked-in chain's facts or explicit revision settings. That
static cross-check is removed at the operator's request. Runtime protection
remains: missing declared facts fail manifest creation; dates come from capture
filenames; contradictory, absent or multiple capture dates fail. The loader
intentionally accepts an explicit revision, so the deleted revision assertion
was a chain-policy check rather than a runtime requirement.

Surviving behavior coverage:
- `tests/mdm/test_read_units.py::test_a_run_without_the_declared_facts_is_refused`
- `tests/mdm/test_read_units.py::test_a_step_naming_an_undeclared_fact_is_refused`
- `tests/unit/test_rules_loading.py::test_a_delivery_takes_its_date_and_its_order_from_the_captures_file_names`
- `tests/unit/test_rules_loading.py::test_a_date_typed_against_the_captures_own_or_a_capture_stating_none_or_two_stops_the_load`
- `tests/unit/test_load_chain.py::test_the_arguments_follow_the_step`

Mutation reasoning: bypassing the runtime missing-facts check is caught by
`test_a_run_without_the_declared_facts_is_refused`; dropping date conflict
handling is caught by the surviving load failure journey. Introducing an
incorrect fact or revision only in the chain configuration no longer has these
two early static guards; it must be found by runtime validation or load proof.

After the requested deletion, the existing `test_load_chain.py`,
`test_rules_loading.py` and `test_read_units.py` files pass together:
195 passed in 6.70s with `pytest --testmon --testmon-noselect`.

## Ownership coordination

The overlap guard identifies uncommitted finish-related changes in another
session's `tests/unit/test_load_chain.py`, under
`claude/links-reads-one-pass`. Those are different functions from the two
requested deletions. The operator explicitly approved only the two named deletions despite the
shared-file overlap. Their scope excludes the other session's finish functions.
The narrow exception permits this commit without changing that worktree or
weakening the guard. The previous automatic merge command was stopped so this
revised scope receives its own full CI gate.

The follow-up Standards, Spec and GoF reviews found no actionable issues in
the retirement, with the unique static configuration protection lost stated above.
