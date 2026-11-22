# Capability gap: compare can replace approved findings

Type: task
Status: resolved
Priority: P0
Blocked by: none
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)

## Question

How does `profile_data.py compare` preserve the approved findings it compares against, whatever `--out` is supplied?

## Evidence

Ticket 11's changed-delivery scenario requires approved findings to remain unchanged. The prior probe on invented inputs returned 0 and wrote `drift.yaml`, but also rewrote `findings.yaml` as a draft plus `REPORT.md`, `fingerprints.json` and `invalid_rows.jsonl` when `--out` was the approved folder. The skill's old compare example used the same placeholder folder for `--approved` and `--out`, so following it could overwrite the baseline.

This change compares resolved paths before fingerprint loading or profiling and refuses when `--out` is the directory containing `--approved`. `tests/unit/test_profiling_run.py::test_compare_lists_drift_and_preserves_approved_findings` approves an invented baseline, compares a changed delivery into a separate folder, then attempts the same-folder compare. It captures SHA-256 values for the findings and adjacent artifacts before and after both calls, asserts equality, and asserts no `drift.yaml` appears in the approved folder. The earlier pre-fix probe did not retain literal digest strings; the regression test computes before/after values at runtime and does not freeze a generated hash.

Local proof after rebasing onto latest `origin/main` (`2956c2def9`): `TESTMON_DATAFILE=/tmp/testmon-compare-safety-after-2027 uv run --no-sync pytest --testmon tests/unit/test_profiling_run.py` — 46 passed in 17.36s; skill-length check — 6 passed in 0.19s; genericity lint — 145 passed in 0.21s. Invented temporary fixtures only; no provider requests or source data.

## Required behavior

- `compare` refuses before writing anything when `--out` holds approved findings, including the folder containing `--approved`.
- The skill names a separate output folder from the approved baseline.
- A test on invented inputs verifies refusal and that approved `findings.yaml` retains its sha256.

## Acceptance checklist

- [x] Prior probe reproduced the destructive same-folder behavior on invented inputs; the regression test captures before/after findings SHA-256 and verifies equality after the fix. (2026-11-22 07:41 ET; the earlier probe did not retain literal digests.)
- [x] Add a generic pre-write refusal and a test proving the approved findings and adjacent artifact hashes remain unchanged; local focused test: 46 passed, skill-length test: 6 passed, and genericity lint: 145 passed after latest rebase. (2026-11-22)
- [x] Update both Data Profiling compare examples to use a distinct private output folder and document the pre-write refusal. PR #2015 is merged, so the update is based on its current skill text. (2026-11-22)
- [x] Publish this ticket's change in draft PR #2030; all 12 CI jobs passed on code head `36df9a052d` in run `45070323188`. The closeout-only head still requires CI before merge.
- [x] Learning → skill: the separate-output and approval-preservation rule is in Data Profiling's compare guidance. (2026-11-22)


## Ticket 11 linkage

[Ticket 11](./11-data-profiling-generic-verification.md) remains incomplete until its other approved scenarios are run. The compare capability described above is now implemented and verified on invented inputs.
