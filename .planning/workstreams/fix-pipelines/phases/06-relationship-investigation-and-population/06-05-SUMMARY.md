---
phase: 06-relationship-investigation-and-population
plan: 05
subsystem: mdm
tags: [sec-companyfacts, xbrl, dei, source-coverage-exclusion, 5-whys]

requires:
  - phase: 06-03
    provides: EDGE-10 coverage classification (ARTIFACT PRESENT, SILVER EMPTY) and fundamental-factors-v2 coordination context
provides:
  - EDGE-10 (AUDITED_BY) disposed as a documented source-coverage exclusion, with the exact SEC API limitation identified
affects: [06-06]

tech-stack:
  added: []
  patterns: ["ix:nonNumeric vs ix:nonFraction XBRL fact-type distinction for SEC companyfacts API coverage"]

key-files:
  created:
    - .planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-05-EDGE10-DISPOSITION.md
  modified: []

key-decisions:
  - "EDGE-10 disposed as a source-coverage exclusion, not populated: the SEC companyfacts aggregate API structurally never surfaces ix:nonNumeric-tagged DEI facts (AuditorFirmId/AuditorName/AuditorLocation), confirmed via live evidence + a clean control, not inferred from absence alone."
  - "No new deriver code written -- _derive_audited_by confirmed correct as-is for the data shape it's given; the gap is entirely upstream in which SEC endpoint the platform fetches from."
  - "Resolving EDGE-10 would require a new per-filing inline-XBRL ingestion path (parsing each 10-K's own cover-page facts directly) -- explicitly out of this plan's scope (Rule 4, architectural change), not attempted here."
  - "Task 1's blocking coordination checkpoint was approved by the operator before Task 2/3 proceeded -- fundamental-factors-v2 (Codex) confirmed tombstoned/merged, no coordination overlap existed."

patterns-established:
  - "When investigating why an SEC companyfacts-derived silver table is empty despite the fetch having run, distinguish ix:nonFraction (numeric, unit-bearing) facts -- which the aggregate API surfaces -- from ix:nonNumeric (text-typed) facts, which it does not. Confirm with a same-filing control fact (e.g. dei:EntityRegistrantName) to rule out concept-specific exclusion vs. systemic fact-type exclusion before concluding a source-coverage gap."

requirements-completed: [EDGE-10]

duration: ~20min (across two worktree executor attempts; the second completed all real work but stalled before its final commit -- work rescued and committed by the orchestrator)
completed: 2026-07-12
---

# Phase 06 Plan 05: EDGE-10 (AUDITED_BY) Disposition Summary

**AUDITED_BY disposed as a documented source-coverage exclusion: SEC's companyfacts aggregate API structurally never surfaces the ix:nonNumeric-tagged auditor DEI facts (AuditorFirmId/AuditorName/AuditorLocation), confirmed via live SEC EDGAR evidence across 3 unrelated filers plus a clean control fact.**

## Performance

- **Duration:** ~20 min across two worktree executor attempts (first delivered the Task 1 coordination-gate finding before a session-limit kill; second completed Task 2/3's full root-cause investigation but stalled 600s before its final SUMMARY.md/commit step — third consecutive transient infra failure this wave, none a logic bug)
- **Completed:** 2026-07-12
- **Tasks:** 3 (coordination gate, root-cause, disposition)
- **Files modified:** 1 (the disposition doc, built incrementally across both executor attempts)

## Accomplishments
- **Task 1 (approved by operator):** confirmed the entity-facts fetch prerequisite was already present in the loaded 150-CIK universe (`sec_financial_fact`: 2,729,147 rows; `sec_financial_derived`: 28,552 rows) — no fresh fetch run needed. Also independently re-confirmed `fundamental-factors-v2` (Codex) is tombstoned/merged into this workstream, mooting the coordination concern.
- **Task 2 root cause:** proved via live SEC EDGAR API calls (no dev AWS access in the execution environment) that `sec_accounting_flag.auditor_pcaob_id = 0` is not a parser or write-path bug. The SEC `companyfacts` aggregate API — the exact endpoint `bootstrap-fundamentals entity-facts` calls — never includes `ix:nonNumeric`-tagged DEI facts (`AuditorFirmId`, `AuditorName`, `AuditorLocation`) in its response, for any company. Confirmed on 3 unrelated large-cap filers (Apple, Microsoft, NVIDIA); ruled out "auditor-specific" exclusion via a clean control (`dei:EntityRegistrantName` — also `ix:nonNumeric`, present on every 10-K, unrelated to auditor data — likewise absent from all three companyfacts responses). Confirmed the actual data exists at SEC: Apple's FY2025 10-K inline XBRL directly tags PCAOB ID 42 (Ernst & Young LLP, San Jose CA) — it's a fetch-path gap, not a data-absence gap.
- **Task 3 disposition:** AUDITED_BY excluded as a documented source-coverage gap. `_derive_audited_by` (`edgar_warehouse/mdm/pipeline.py:1214-1330`) confirmed correct as-is — no code changed. Since the source table's auditor columns are deterministically NULL for every row (a structural API limitation, not a transient/re-fetchable condition), running the derivation now would produce 0 rows with no new evidence beyond Task 2's findings, so it was not run. AUDITED_BY graph edge count: 0 (documented exclusion, not an undocumented zero state).

## Task Commits

1. **Task 1: Coordination gate finding (rescued after session-limit kill)** — `3710fa1` (wip, rescued from a killed executor's uncommitted worktree state)
2. **Task 2 + Task 3: Root-cause + exclusion disposition (rescued after stall)** — `d1430aa` (fix, rescued from a stalled executor's uncommitted worktree state)

**Plan metadata:** this SUMMARY.md (docs: complete plan)

_Note: Both prior commits represent orchestrator-rescued work from two separate worktree executor attempts, each killed by a different transient infrastructure failure (API session limit, then a 600s stall) after completing real, valid work but before their own final commit/SUMMARY step._

## Files Created/Modified
- `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-05-EDGE10-DISPOSITION.md` — full coordination-gate record, 5-whys root cause, and source-coverage exclusion disposition

## Decisions Made
- EDGE-10 disposed as a source-coverage exclusion rather than "populated" or a false zero state — the distinction matters because the underlying cause (aggregate-API fact-type filtering) is structural and will not resolve itself via re-fetching, unlike a transient or environment-specific gap.
- No speculative fix was applied to `parse_entity_facts`/`merge_accounting_flags`/`_derive_audited_by` — all three are confirmed correct for the data shape SEC's companyfacts API actually delivers; the gap is entirely upstream in endpoint selection, and "fixing" any of these three would not change the outcome.
- Resolving EDGE-10 for real would require a new per-filing inline-XBRL ingestion path (parsing each 10-K's own cover-page facts directly, similar to the existing per-filing bootstrap-fundamentals mode) — explicitly scoped out as an architectural change (Rule 4), not attempted in this plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Environment constraint] Worktree execution environment lacked dev (690839588395) AWS access**
- **Found during:** Task 2's root-cause investigation, which the plan's ideal case assumed would run against the dev `silver.duckdb`.
- **Issue:** AWS credentials in the worktree-isolated executor's environment did not reach the active dev account (same constraint documented in 06-04's SUMMARY.md).
- **Fix:** Root-caused entirely via live, read-only calls to the public SEC EDGAR API (`data.sec.gov`, `www.sec.gov`) against real filings — a strictly stronger form of evidence than a single dev-universe data pull, since it demonstrates the API limitation is universal (3 unrelated filers), not specific to the loaded 150-CIK universe.
- **Files modified:** None (environmental, not code)
- **Verification:** N/A — documented, evidence-based finding
- **Committed in:** `d1430aa`

**2. [Rule — transient infra] Two consecutive worktree executors killed by different transient failures**
- **Found during:** Both continuation attempts for Task 2/3.
- **Issue:** First continuation attempt made no progress before a session-usage-limit kill (worktree was clean, safely discarded). Second continuation attempt completed all real investigative work (the full Task 2/3 disposition, verified against the plan's exact acceptance criteria) but stalled for 600s right before its final SUMMARY.md/commit step.
- **Fix:** Inspected the second worktree's uncommitted diff before cleanup, verified it satisfied the plan's automated verify (`grep` for "AUDITED_BY" + "source-coverage exclusion" — both present) and acceptance criteria (exclusion named, no new deriver code, correct branch taken), then rescued and committed it directly rather than discarding or re-running a third time.
- **Files modified:** None beyond the rescue commit (already tracked above)
- **Verification:** Manual review against `06-05-PLAN.md`'s Task 2/3 `<verify>`/`<acceptance_criteria>` blocks — all satisfied.
- **Committed in:** `d1430aa`

---

**Total deviations:** 2 (1 environmental constraint honestly worked around with equal-or-better evidence, 1 transient-infra recovery via commit rescue — no scope creep)
**Impact on plan:** Both tasks reach their full intended disposition (Task 2 root-cause confirmed, Task 3 exclusion documented) despite neither worktree environment having live dev access — the live-SEC-API evidence approach is arguably stronger than a single dev-universe check would have been.

## Issues Encountered
Three consecutive subagent dispatches across this plan and its sibling (06-04) hit transient infrastructure failures this session (a session usage limit, an API "Connection closed" error, and a 600s stall) — none were logic or plan defects. Each was diagnosed via post-mortem worktree inspection (commits/diffs vs. clean) rather than blind retry, consistent with CLAUDE.md's 5-whys debugging discipline, and valid work was rescued rather than discarded or redone from scratch in every case.

## Next Phase Readiness
- **06-06** (EDGE-05/06 closure + phase ledger) can proceed — EDGE-10's disposition is recorded and does not block it.
- No concrete outstanding infra step for EDGE-10 (unlike EDGE-11 in 06-04) — this is a closed exclusion, not a pending fix. A future milestone could scope a new per-filing inline-XBRL ingestion path if AUDITED_BY population becomes a priority, but that is new work, not a follow-up to this plan.

---
*Phase: 06-relationship-investigation-and-population*
*Completed: 2026-07-12*
