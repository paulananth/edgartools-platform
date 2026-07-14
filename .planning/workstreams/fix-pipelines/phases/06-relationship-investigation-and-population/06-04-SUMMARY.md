---
phase: 06-relationship-investigation-and-population
plan: 04
subsystem: mdm
tags: [bronze-fetch, 13f-hr, def-14a, sec-parsers, edgartools, 5-whys]

requires:
  - phase: 06-03
    provides: EDGE-09/EDGE-11 coverage classification (ARTIFACT PRESENT, SILVER EMPTY for both)
provides:
  - EDGE-11 (INSTITUTIONAL_HOLDS) root cause and committed fix: 13F-HR bronze fetch fast-path
    never discovered the INFORMATION TABLE attachment
  - EDGE-09 (EMPLOYED_BY) root-cause investigation, honestly left open pending dev silver access
affects: [06-06, 06-05]

tech-stack:
  added: []
  patterns: ["form-type-gated bronze fetch fast path"]

key-files:
  created:
    - .planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-04-EDGE09-EDGE11-DISPOSITION.md
  modified:
    - edgar_warehouse/bronze_filing_artifacts.py
    - tests/unit/test_loader_idempotency.py

key-decisions:
  - "EDGE-11: fixed at the root cause (bronze fetch attachment discovery), not the XML parser or the attachment-matching logic in fundamentals_ingest.py -- both were already correct."
  - "EDGE-09: left as an honestly-documented open item rather than applying a speculative parser-heuristic fix that could not be verified against the actual failing dev-universe filings (no dev AWS access in the execution environment)."
  - "Neither type is mischaracterized as a source-coverage exclusion -- both artifacts are present and fetchable; EDGE-09/EDGE-11 needed root-cause work, not exclusion documentation."

patterns-established:
  - "Bronze-fetch fast path (fetch_filing_artifacts) must be form-type-gated: it is only valid when the primary document IS the complete substantive content (true for Form 3/4/5), and must be bypassed for forms where holdings/data live in a separate non-primary attachment (13F-HR's INFORMATION TABLE)."

requirements-completed: [EDGE-09, EDGE-11]

duration: ~15min (across two worktree executor attempts, both interrupted by transient API connection errors; work merged from the first attempt's 2 valid commits)
completed: 2026-07-12
---

# Phase 06 Plan 04: EDGE-09/EDGE-11 Disposition Summary

**Root-caused and fixed EDGE-11's 13F-HR bronze-fetch attachment-discovery bug (INFORMATION TABLE never fetched); EDGE-09 (DEF 14A proxy parser) root-caused to two plausible non-bug explanations but left as an honestly documented open item pending dev silver access.**

## Performance

- **Duration:** ~15 min of actual executor work (two dispatch attempts; both worktree-isolated executors were killed mid-run by transient API "Connection closed" errors, not logic failures — first attempt's 2 commits were valid, tested, and merged rather than discarded)
- **Completed:** 2026-07-12
- **Tasks:** 2 (EDGE-09 investigation, EDGE-11 root-cause + fix)
- **Files modified:** 3

## Accomplishments
- **EDGE-11 real bug found and fixed:** `fetch_filing_artifacts`'s bronze-fetch "fast path" (written for Form 3/4/5 ownership filings, where the primary document is the complete substantive content) was never form-type-gated, so it silently applied to 13F-HR too — registering only the primary cover-page document and never invoking the edgartools attachment-enumeration fallback that would discover the separate, non-primary INFORMATION TABLE attachment holding the actual 13F holdings data. Every 13F-HR filing hit `run_bootstrap_thirteenf`'s `thirteenf_no_infotable` skip path as a result.
- Live-verified both the XML parser (`parse_thirteenf` against a real Berkshire Hathaway 13F-HR INFORMATION TABLE — 90 holding rows extracted correctly) and the proxy parser (`parse_proxy_fundamentals` against a real Apple DEF 14A — 5 executive comp rows extracted correctly) to isolate the defects to the fetch layer, not the parsers.
- Fix: gated the fast path on `form_type not in {"13F-HR", "13F-HR/A"}`; those two forms now always take the existing (already-correct) edgartools attachment-enumeration path. Ownership/ADV/DEF14A/8-K fast-path behavior is unchanged.
- 2 new regression tests added; all 9 tests in `test_loader_idempotency.py` pass.
- EDGE-09 (EMPLOYED_BY): ruled out an import/dependency/wholesale parser break via live testing, but could not conclusively reproduce the dev-universe-specific zero-count without dev silver access (this execution environment's AWS credentials resolved to the decommissioned `077127448006` account). Documented two plausible non-bug explanations (DEFA14A supplemental material lacking an SCT; Smaller Reporting Company scaled Item 402 disclosure) as a scoped follow-up rather than asserting an unverified fix.

## Task Commits

1. **Task 1: EDGE-09 root-cause + disposition doc** — `ba1e0d3` (docs)
2. **Task 2: EDGE-11 root-cause + fix** — `0d3db31` (fix)
3. **Merge into claude/consolidate-workstreams** — `eb8b276` (chore)

## Files Created/Modified
- `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-04-EDGE09-EDGE11-DISPOSITION.md` — full 5-whys, fix rationale, and disposition for both types
- `edgar_warehouse/bronze_filing_artifacts.py` — `_MULTI_ATTACHMENT_FORMS` form-type gate on the fast path
- `tests/unit/test_loader_idempotency.py` — 2 new regression tests for 13F-HR/13F-HR-A attachment discovery

## Decisions Made
- EDGE-11 fixed at the actual defect (bronze-fetch attachment discovery), not the XML parser or attachment-matching logic — both were already correct; a symptom-level patch elsewhere would have masked the real bug.
- EDGE-09 left open rather than applying a speculative parser-heuristic loosening that could not be verified against the real failing filings — avoids a false-green fix.
- Neither type is recorded as a source-coverage exclusion: both artifacts are present, fetchable, and (for EDGE-11) now correctly discoverable going forward.

## Deviations from Plan

### Auto-fixed Issues

**1. [Environment constraint] Worktree execution environment lacked dev (690839588395) AWS access**
- **Found during:** Both Task 1 (EDGE-09) and Task 2 (EDGE-11) attempted to run the live derive → sync-graph → graph-row-count chain the plan's ideal-case must_haves describe.
- **Issue:** AWS credentials in the worktree-isolated executor's environment resolved to the decommissioned `077127448006` account, not the active dev account. No dev Snowflake/MDM/Step Functions/S3 access was reachable.
- **Fix:** Both dispositions were completed to the maximum extent possible without dev access — code-level root-causing plus live verification against real, directly-fetched SEC EDGAR filings (not dev bronze/silver) — and the disposition doc explicitly records this constraint rather than asserting an unrun graph-verification result.
- **Files modified:** None (environmental, not code)
- **Verification:** N/A — documented limitation, not a bug
- **Committed in:** `ba1e0d3` (disposition doc records this explicitly under "Environment / worktree provenance note")

**2. [Rule — transient infra] Two API connection failures during executor dispatch**
- **Found during:** Both the initial 06-04 worktree dispatch and the first 06-05 continuation dispatch.
- **Issue:** Both subagents were terminated mid-response by "Connection closed mid-response" API errors — a transient infrastructure issue, not a plan or logic defect.
- **Fix:** Inspected each dead worktree before cleanup. 06-04's worktree had 2 valid, tested commits (`ba1e0d3`, `0d3db31`) — merged into the main branch rather than discarded, verified via `pytest` post-merge. 06-05's continuation worktree was clean (no progress) — safely discarded, to be retried.
- **Files modified:** None beyond the merge itself (already tracked above)
- **Verification:** `pytest tests/unit/test_loader_idempotency.py` — 9/9 passed, both before and after merge into the main branch (confirming no silent conflict with this session's unrelated concurrent artifact-throttle fix to the same two files).
- **Committed in:** `eb8b276` (merge commit)

---

**Total deviations:** 2 (1 environmental constraint honestly documented, 1 transient-infra recovery via commit rescue — no scope creep, no code changes beyond the plan's own scope)
**Impact on plan:** EDGE-11 reaches "root-caused + fixed + unit-tested" but not "graph-verified populated" (blocked on dev AWS access, not on this plan's work). EDGE-09 reaches "root-caused to the extent possible" and is correctly left open rather than falsely resolved.

## Issues Encountered
Two subagent dispatches were killed by transient "Connection closed mid-response" API errors (see Deviations above). Both were root-caused via post-mortem worktree inspection (commits vs. clean) rather than blind retry, per CLAUDE.md's 5-whys debugging discipline.

## Next Phase Readiness
- **06-06** (EDGE-05/06 closure + phase ledger) can proceed — no dependency on EDGE-09/EDGE-11 reaching graph-verified status, only on their dispositions being recorded (done).
- **Concrete outstanding step for an operator/agent with dev (`690839588395`) AWS access**, recorded in the disposition doc:
  - EDGE-11: rebuild+deploy the warehouse image with this fix, then `edgar-warehouse bootstrap-fundamentals --mode thirteenf --cik-list <61 CIKs> --force` (DEC-009-compliant explicit repair) → `mdm derive-relationships --relationship-type INSTITUTIONAL_HOLDS` → `mdm sync-graph` → graph-side count confirmation.
  - EDGE-09: pull the actual dev silver bronze HTML for the 11 DEF 14A + 12 DEFA14A accessions (read-only, same method 06-03 Task 3 used) and run `parse_proxy_fundamentals` against each to determine per-filing whether it's a legitimate empty result or a genuine extractor heuristic miss.
- Not blocking: this plan's own scope (root-cause + disposition) is complete; the above is follow-up infra work, not part of 06-04's deliverable.

---
*Phase: 06-relationship-investigation-and-population*
*Completed: 2026-07-12*
