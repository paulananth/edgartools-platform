# data-profiling: Measure effectiveness

Type: task
Status: resolved
Priority: P0
Blocked by: 06, 11
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)
Step: 6 of 6
Skill dependencies: data-platform
Applicability: Every new captured dataset; compare mode only when an approved delivery changes.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a multi-part archive with two encodings, repeated issued identifiers, an unreadable member and a changed delivery. Measure time to first material finding, repeated scans, unaccounted parts and incorrect type or identifier inference. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-profiling/SKILL.md: Modes, Profile once, How to work, Compare a new delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-profiling: Specify generic verification](./11-data-profiling-generic-verification.md)

Priority rationale: Reusable evidence is the input to every source model.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Pin both revisions, the four paired repetitions, scoring and targets in [Comparison protocol](#comparison-protocol) before running the CLI. (2026-11-24 20:35 ET)
- [x] Compare matching invented archive, numeric, repeat and changed-delivery tasks; recorded four trials per revision with the same local dependencies and no operator or queue wait. (2026-11-24 20:35 ET)
- [x] Report observed pass counts, timing, regressions and limits in [Answer](#answer). (2026-11-24 20:35 ET)
- [x] Publish the comparison on its own branch in [docs(profiling): record paired effectiveness comparison](https://github.com/paulananth/edgartools-platform/pull/2125); documentation genericity: **155 passed**. (2026-11-24 20:36 ET)
- [x] Learning → skill: none. The measured gains come from existing profiler fixes; this probe does not isolate skill wording or justify another wording change. (2026-11-24 20:35 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Comparison protocol

- Baseline `4881e8322909888860db576f65730bc4889dc5a4` (parent of the profiling entrypoint merge; skill tree `392e17e89938aab93d9a8b93efa06cadb0fb647a`); revised `4422b8ff1f3effb342e9976529f0f319def02bf6` (skill tree `e202f80106d600e6b10f0013bbba29cac81f7c02`).
- Compare the documented workflows by running each revision's own CLI on the same invented inputs. Carry forward the archive, numeric, unchanged-run and delivery-drift answer keys from [data-profiling: Specify generic verification](./11-data-profiling-generic-verification.md). Use its published test's six-part fixture for changed delivery (added column and weakened or broken link); do not count fixture setup or approval marking as timed work. Mark only synthetic findings as approved for the probe; this is not operator approval of a source.
- Four paired repetitions on one machine, serial, alternating which revision runs first. Use fresh output folders, shared input paths and the same Python/DuckDB/PyYAML. Report median wall seconds from child-process launch to exit with the first usable `findings.yaml` or `drift.yaml`; the repeat uses its reuse receipt. Report elapsed times for failed gates separately rather than treating them as a fast correct result. No operator or remote queue wait; elapsed includes interpreter startup, local scheduling and I/O.
- Revised targets: zero unaccounted archive members (readable with hashes or explicitly skipped with reason), correct inferred encoding and unreadable warning, zero repeated full profiling passes for identical inputs (reuse receipt plus approved artifacts byte-identical), and zero incorrect or missing numeric/identifier inferences. Score consistency on five named checks: padded repeated identifier storage/distinct count, record-key and derived-entity cardinality, exact decimal storage/scale and output type, wide JSON identifier distinct count and safe output type, and ordinary count/date/boolean types. Require changed-delivery drift, separate output and preservation of approved artifacts. For each matched material result produced correctly by both arms, target revised median no more than 10% above baseline; treat any missing correct baseline as not comparable for correctness-adjusted timing.
- Keep verified improvements, report every missed bar, and do not infer a wording change from command-only timings. No source data, provider requests, model calls, load, or catalog publication. File fingerprinting is not counted as a repeated full profiling pass.

## Answer

The revised executable workflow passed all five numeric and identifier checks in all four trials, up from two of five per baseline trial. It also refused to overwrite the approved findings during compare. Both revisions accounted for all four archive members, reused unchanged findings and identified drift with separate output. The evidence supports keeping the revised workflow; it does not show that the revised skill prose alone improves agent performance.

| Outcome | Baseline | Revised | Target |
|---|---:|---:|---|
| Archive report, median seconds | 0.4993 | 0.4866 | Met; correct encoding and unreadable warning in 4/4 trials per revision; zero unaccounted members |
| Identical-input reuse, median seconds | 0.1052 | 0.1033 | Met; 4/4 reuse receipts per revision, zero repeated profiling passes, all approved artifacts unchanged |
| Numeric/identifier checks, across all trials | 8/20 | 20/20 | Met; decimal, wide JSON identifier and ordinary-type checks all improved from 0/4 to 4/4; padded identifiers and repeated-key/entity checks stayed at 4/4 |
| Separate-output drift, median seconds | 1.0039 | 1.0541 | Met; 5.0% slower, within 10%; both revisions found the added column and weakened or broken link and preserved approved artifacts in 4/4 trials |
| Compare into approved folder | 0/4 refused | 4/4 refused | Met; baseline exited 0 and changed approved files in every disposable trial; revised exited 1 and wrote nothing there |

The numeric command exited 0 in every trial but the baseline output failed the answer key. Raw command medians were 0.5447 s baseline and 0.5664 s revised, **not comparable as time to a correct finding**. The same-folder gate is also not a speed comparison: the baseline did the forbidden work (median 1.0081 s), while the revised version refused (median 0.1846 s). All other measured commands exited 0.

### Reproduction and limits

- On Darwin arm64, run `profile_data.py` from each pinned `skills/data-profiling/scripts` tree using Python 3.12.13, DuckDB 1.5.2 and PyYAML 6.0.3. Use `run` with fixed defaults and a fresh output folder, mark synthetic findings approved, then repeat with identical arguments; compare the four artifact hashes (`findings.yaml`, `REPORT.md`, `fingerprints.json`, `invalid_rows.jsonl`). For changed delivery, use `compare` once into a new folder and once into the disposable approved folder. Compare artifacts against their own pre-command hashes, never with retired implementation output as the correctness oracle.
- Inputs and independent assertions are in `test_profiling_run.py` (`_write_profile_archive`, `test_approved_archive_run_reuses_unchanged_findings_and_fingerprints`, `test_compare_lists_drift_and_preserves_approved_findings`) and `test_data_profiling_exact_numbers.py` (`test_mixed_inputs_keep_repeated_identifiers_and_exact_decimals`). Each paired repetition used the same input paths and bytes. One baseline archive run took 1.1778 s; small-sample medians are descriptive, with no cold-cache or production throughput claim.
- Command elapsed time includes local I/O and interpreter startup; neither arm needed operator input, dependency installation during timing, a provider, or remote compute. It is a proxy for first usable evidence, not time for a person or agent to read and interpret it. The installed `SKILL.md` hashes differently from the revised repository copy and was not run. No real source readiness, production performance or skill-prose effect was measured.
