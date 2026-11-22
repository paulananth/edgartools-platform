# data-profiling: Specify generic verification

Type: task
Status: open
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
- [ ] Use the existing generic path to prove all four scenarios end to end. Tests were added for the archive/unreadable-member and unchanged-run outcomes. Exact decimal/long-integer preservation and compare's refusal to overwrite approved findings are blocked by the linked capability gaps; leave this ticket open until those gaps are fixed and the remaining scenarios pass.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof. New tests invoke the real `profile_data.main` path on invented files. Their outcomes are pending the parent's focused checks; known unsupported outcomes and prior probe evidence are below.
- [ ] Publish this scoped change in a ticket-specific draft PR; keep it draft until current-head CI passes. (2026-11-21 19:43 ET)
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
   - **Outcome:** cannot pass on the current reader. A previous probe on invented inputs found the CSV decimal stored as `DOUBLE` with `decimal_places: 20` instead of 2, and 60 distinct 22-digit JSON identifiers collapsed to 5 distinct values. Recorded in [gap-data-profiling-exact-numbers](./gap-data-profiling-exact-numbers.md); no profiler runtime change was made.
3. **Unchanged run reused.**
   - **Given** scenario 1's findings are approved in `--out`.
   - **When** `run` repeats with identical name, input, settings and profiler.
   - **Then** it prints `reused`; `findings.yaml` and `fingerprints.json` keep their sha256; approval remains approved.
   - **Implementation:** `tests/unit/test_profiling_run.py::test_approved_archive_run_reuses_unchanged_findings_and_fingerprints`. Outcome pending the parent's focused checks. Existing `test_unchanged_inputs_and_profiler_reuse_the_findings` also covers the generic path on the synthetic folder fixture.
4. **Changed delivery.**
   - **Given** approved findings and a second zip in which one readable member gains rows and a new code.
   - **When** `run` repeats into the same `--out`, then `compare` runs once into a separate `--out` and once into the approved folder itself.
   - **Then** `run` refuses to replace approved findings; separate-output `compare` writes `drift.yaml` naming volume and code changes only for the changed part; compare into the approved folder refuses; the approved `findings.yaml` sha256 remains unchanged.
   - **Outcome:** separate-output drift and `run`'s approved-findings refusal have existing generic coverage (`test_compare_lists_drift_against_approved_findings`, `test_unchanged_inputs_and_profiler_reuse_the_findings`). The current `compare` path does not refuse to write into the approved folder: a prior invented-input probe returned 0, wrote drift, and replaced `findings.yaml` with a draft, so the final assertions cannot pass. Recorded in [gap-data-profiling-compare-keeps-approval](./gap-data-profiling-compare-keeps-approval.md). No profiler runtime change was made.

### Stored outcomes, limits and provenance

- New scenario tests use the real profiler entrypoint and temporary invented inputs. Their pass/fail results remain unverified until the parent runs the focused checks. No mock-only, static-text or tautological tests were added.
- Earlier generic tests listed in the original ticket evidence cover unreadable files, single non-UTF-8 CSVs, separate-output compare drift and same-input reuse. They do not cover the four approved scenarios as a whole.
- The archive's top-level input has one overall sha256; a changed member causes the archive input to be profiled again. Reuse is whole-input, not per-member. After approval, a changed delivery uses `compare`.
- The repository skill on this branch is the current `origin/main` copy. The installed `data-profiling` skill was read; it differs from the repository skill and does not include the repository's current `Run this phase` entrypoint/resume guidance. The repo test exercises `skills/data-profiling/scripts/profile_data.py`, not the installed copy.
- No provider request, source load, or mutation of approved real findings was performed. The skill needs no change for the verified reusable lessons: archive member/readme behavior and profile-once reuse are already in `Modes` and `Profile once`.

