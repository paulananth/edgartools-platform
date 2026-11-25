# data-profiling: Specify generic verification

Type: task
Status: resolved
Priority: P0
Blocked by: 05, 10
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)
Step: 5 of 6
Skill dependencies: data-platform
Applicability: Every new captured dataset; compare mode only when an approved delivery changes.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: a multi-part archive with two encodings, repeated issued identifiers, an unreadable member and a changed delivery.

Required observable proof: reuse unchanged findings, detect changed inputs and account for unreadable members while retaining exact identifiers and decimals. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/data-profiling/SKILL.md: Modes, Profile once, How to work, Compare a new delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [data-profiling: Make progress resumable](./10-data-profiling-resume.md)

Priority rationale: Reusable evidence is the input to every source model.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Prerequisites 05 and 10 are merged on `origin/main`: 05 PRs #1983/#1993 and 10 PRs #1986/#1992 are in the branch's history. (2026-11-21 19:43 ET)
- [x] Record distinct Given–When–Then scenarios and obtain approval before test implementation. Main confirmed: “The operator approved the exact four scenarios you listed.” Approval was received before the scenario tests were written. (2026-11-21 19:43 ET)
- [x] Run and record the complete four-scenario set together on the current source and test paths. `tests/unit/test_profiling_run.py` and `tests/unit/test_data_profiling_exact_numbers.py` ran together against `origin/main`: **48 passed in 11.8 s**. Scenario 1: `test_run_reports_both_encodings_and_unreadable_archive_members`; scenario 2: the exact-number suite; scenario 3: `test_approved_archive_run_reuses_unchanged_findings_and_fingerprints`; scenario 4: `test_compare_lists_drift_and_preserves_approved_findings`. (2026-11-24 19:01 ET)
- [x] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof. The tests call the real `profile_data.main` path on invented files; outcomes are in the combined run above, limits under Stored outcomes below. (2026-11-24 19:01 ET)
- [x] Publish the scenario tests through [test(profiling): cover generic archive and reuse scenarios](https://github.com/paulananth/edgartools-platform/pull/2010); the PR is merged and its current-head CI passed.
- [x] Learning → skill: no skill edit. `Modes` already documents zip members/readme handling and `Profile once` already documents identical-run reuse; the new cases exercise those existing claims, not a new rule. (2026-11-21 19:43 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while any checklist item remains open.

## Answer

### Approved Given–When–Then scenarios

The four scenarios below were approved by the operator before implementation; Main relayed the approval: “The operator approved the exact four scenarios you listed.” All fixtures are invented and temporary. Each uses the shared profiler entrypoint, with no source-specific runtime code.

1. **Multi-part archive with two encodings and an unreadable member.**
   - **Given** one zip containing a UTF-8 CSV and a Windows-1252 CSV with different headers, an unreadable member, and a readme.
   - **When** `run` profiles the zip as one input.
   - **Then** findings contain exactly the two readable parts, each with its own `sha256`; the Windows-1252 part has inferred `encoding` with its `declare`; the unreadable member and readme appear under `dataset.not_read` with reasons; and stderr names the unreadable member.
   - **Implementation:** `tests/unit/test_profiling_run.py::test_run_reports_both_encodings_and_unreadable_archive_members`. A second test exercises approval and reuse for the same zip: `test_approved_archive_run_reuses_unchanged_findings_and_fingerprints`. Both tests are pending the parent's focused checks; no local tests were run in this work.
2. **Repeated issued identifiers kept exact.**
   - **Given** a repeating issued identifier with leading zeros beside a name, a decimal with at most two places including a 17-digit integer part, and a separate JSON input with distinct 22-digit integer identifiers.
   - **When** `run` profiles both inputs.
   - **Then** leading zeros remain, the identifier is not a record key and its derived entity has one row per distinct value, the decimal is exact with `decimal_places: 2`, JSON `distinct` equals record count, and no silver type is `DOUBLE`.
- **Resolved after the original probe:** [Capability gap: the profiler reads some numbers through floating point](./gap-data-profiling-exact-numbers.md) is implemented in [fix(data-profiling): preserve exact numeric values](https://github.com/paulananth/edgartools-platform/pull/2015). The regression suite now asserts exact decimal scale and JSON distinct counts.
3. **Unchanged run reused.**
   - **Given** scenario 1's findings are approved in `--out`.
   - **When** `run` repeats with identical name, input, settings and profiler.
   - **Then** it prints `reused`; `findings.yaml` and `fingerprints.json` keep their sha256; approval remains approved.
   - **Implementation:** `tests/unit/test_profiling_run.py::test_approved_archive_run_reuses_unchanged_findings_and_fingerprints`. Outcome pending the parent's focused checks. Existing `test_unchanged_inputs_and_profiler_reuse_the_findings` also covers the generic path on the synthetic folder fixture.
4. **Changed delivery.**
   - **Given** approved findings and a second zip in which one readable member gains rows and a new code.
   - **When** `run` repeats into the same `--out`, then `compare` runs once into a separate `--out` and once into the approved folder itself.
   - **Then** `run` refuses to replace approved findings; separate-output `compare` writes `drift.yaml` naming volume and code changes only for the changed part; compare into the approved folder refuses; the approved `findings.yaml` sha256 remains unchanged.
- **Resolved:** the same-folder compare refusal and baseline preservation are implemented in [Capability gap: compare can replace approved findings](./gap-data-profiling-compare-keeps-approval.md). The parent ticket still needs its combined scenario evidence.

### Stored outcomes, limits and provenance

- New scenario tests use the real profiler entrypoint and temporary invented inputs. Archive/unreadable and unchanged-run scenarios passed in PR2010 CI; the exact-number/input suite passed 59 tests locally on 2026-11-23. The combined four-scenario run then passed (48 tests); the ticket is resolved.
- Earlier generic tests listed in the original ticket evidence cover unreadable files, single non-UTF-8 CSVs, separate-output compare drift and same-input reuse. They do not cover the four approved scenarios as a whole.
- The archive's top-level input has one overall sha256; a changed member causes the archive input to be profiled again. Reuse is whole-input, not per-member. After approval, a changed delivery uses `compare`.
- The repository skill on this branch is the current `origin/main` copy. The installed `data-profiling` skill was read; it differs from the repository skill and does not include the repository's current `Run this phase` entrypoint/resume guidance. The repo test exercises `skills/data-profiling/scripts/profile_data.py`, not the installed copy.
- No provider request, source load, or mutation of approved real findings was performed. The skill needs no change for the verified reusable lessons: archive member/readme behavior and profile-once reuse are already in `Modes` and `Profile once`.
- PR2010 is merged; its current-head CI passed. The exact-number fix is in PR2015. This parent ticket remains open until its four-scenario evidence is recorded together.

## Comments

- 2026-11-23: The test-order failure was shared fixture state: `test_approve_records_exact_words` mutated the module-scoped `findings.yaml`, while the catalog-summary test assumed that side effect. The catalog-summary test now writes its own draft findings copy and approves it through `profile_data.main` before catalog publication. The isolated test failure was reproduced before the fix; the full `tests/unit/test_profiling_run.py` file now passes with `--testmon-noselect` (46 tests). No profiler runtime code changed. The parent ticket remains open for the combined four-scenario evidence run.

