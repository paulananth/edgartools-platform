---
phase: 06-relationship-investigation-and-population
plan: 06
subsystem: mdm
tags: [source-coverage-exclusion, artifact-fetch-gate, root-cause, closure-ledger, 5-whys]

requires:
  - phase: 06-04
    provides: EDGE-11 bronze-fetch fast-path fix (committed, unit-tested); EDGE-09 initial investigation (superseded)
  - phase: 06-05
    provides: EDGE-10 source-coverage exclusion (structural SEC API limitation)
provides:
  - EDGE-05/EDGE-06 disposed as source-coverage exclusions (D-04 SQL-confirmed zero-overlap)
  - EDGE-09's root cause found and documented (supersedes 06-04's "open item")
  - EDGE-11's disposition corrected: fix is real but unreachable via the standard bulk pipeline
  - Phase 6 closure ledger: all 5 relationship types (EDGE-05/06/09/10/11) each in exactly one evidenced disposition
  - REQUIREMENTS.md traceability reconciled (removes premature "Complete" status for EDGE-09/EDGE-11)
affects: [phase-7]

tech-stack:
  added: []
  patterns:
    - "When a bulk relationship-derivation table is unexpectedly empty despite present filing metadata, check the artifact-fetch SELECTION gate (which forms get sec_filing_attachment/sec_raw_object populated at all) before assuming a parser bug -- a silent 'primary is None' skip with no error log looks identical to a parser returning zero rows."
    - "A single ad-hoc/targeted-resync code path can create a tiny amount of real data (e.g. 23 attachment rows) that masks a systemic bulk-pipeline gap affecting the other 99.9%+ of the same form type -- verify coverage platform-wide, not just for the one sample that happens to work."

key-files:
  created:
    - .planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-PHASE-CLOSURE-LEDGER.md
  modified:
    - .planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-06-EDGE05-EDGE06-DISPOSITION.md (Task 1, committed prior session as d375964)
    - .planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-04-EDGE09-EDGE11-DISPOSITION.md (2026-07-13 update sections superseding the EDGE-09 open item, correcting EDGE-11)
    - edgar_warehouse/mdm/snowflake_graph.py (docstring comment updated; POPULATED_RELATIONSHIP_TYPES intentionally unchanged)
    - .planning/workstreams/fix-pipelines/REQUIREMENTS.md (EDGE-05/06/09/10/11 checkboxes + Traceability table reconciled to ledger)

key-decisions:
  - "EDGE-09 and EDGE-11 share one root cause: _is_configured_parser_form (warehouse_orchestrator.py:1859-1861) gates the bulk artifact-fetch pipeline to OWNERSHIP_FORMS/ADV_FORMS only, so DEF14A/DEFA14A/8-K/13F-HR filings never get sec_filing_attachment populated at scale -- confirmed via live Step Functions execution history, CloudWatch logs, and platform-wide silver queries."
  - "Introduced a third disposition category (ROOT-CAUSED / FIX DEFERRED) alongside POPULATED and EXCLUDED, since EDGE-09/EDGE-11 are neither a source-coverage exclusion (the artifact IS present and fetchable, the parser IS correct) nor populated (no rows exist) -- forcing either label would misrepresent a fixable gap. Satisfies Success Criterion 6 (documented, evidenced, not silent) without a false binary."
  - "Did not widen _is_configured_parser_form to fix EDGE-09/EDGE-11 in this session, per advisor guidance: doing so would multiply bulk SEC artifact-fetch volume by roughly the size of the 8-K/DEF14A/13F-HR form populations (~266k + ~52k + ~49k filings), a capacity/cost decision requiring explicit user scoping, not an inline same-session fix. It also would not by itself change either type's disposition -- reaching 'populated' still requires deploy + bulk re-fetch + re-derive + sync + graph-count, none of which is inline-executable."
  - "POPULATED_RELATIONSHIP_TYPES left unchanged (no additions) -- correctly a no-op this phase since none of the 5 investigated types reached graph-verified-populated status. Per D-05's sequencing guard, adding any of them now would false-fail verify-graph's named parity check for a type never actually synced to the graph."
  - "REQUIREMENTS.md's premature [x] Complete status for EDGE-09 and EDGE-11 (set during the 2026-07-11 consolidation commit, before this phase's plans actually ran) is corrected: both are now [ ] with an explicit 'not marked Complete' note, since the underlying relationships are still zero -- only the zero state is now fully explained, not resolved."

patterns-established:
  - "5-whys for 'derived relationship table is empty': (1) deriver has nothing to read -> (2) source silver table is empty -> (3) parser produces zero rows? Test directly against real captured bytes, not a live external re-fetch, using the exact decode path the production caller uses -> (4) if parser is correct, check whether the per-filing/per-accession loop is even reaching the parser (silent skip vs. logged error) -> (5) if silently skipped, check the upstream artifact-fetch SELECTION gate, not just the fetch mechanism itself."

requirements-completed: []
requirements-partially-addressed: [EDGE-05, EDGE-06, EDGE-09, EDGE-10, EDGE-11]

duration: ~90min (inline execution, no subagents, per explicit user instruction)
completed: 2026-07-13
---

# Phase 06 Plan 06: EDGE-05/06 Closure, POPULATED_RELATIONSHIP_TYPES Review, and Phase Closure Ledger

**EDGE-05/EDGE-06 disposed as source-coverage exclusions via a live D-04 SQL zero-overlap check; EDGE-09's previously-open root cause was found (shared with EDGE-11) via live dev AWS access; the phase closure ledger records all 5 relationship types in exactly one evidenced disposition, with REQUIREMENTS.md corrected to match.**

## Performance

- **Duration:** ~90 min, executed entirely inline in the main working directory per explicit user instruction ("dont spinup parallel agents") — no subagents dispatched this plan.
- **Completed:** 2026-07-13
- **Tasks:** 3 (D-04 closure, POPULATED_RELATIONSHIP_TYPES review, phase closure ledger) plus one unscoped-but-valuable side investigation (EDGE-09 root cause) that resolved a real gap in 06-04's original disposition.

## Accomplishments

- **Task 1 (completed prior session, commit `d375964`):** EDGE-05 (IS_ENTITY_OF) and EDGE-06 (IS_PERSON_OF) closed via a live D-04 SQL check against dev MDM Postgres, independently mirroring `AdviserResolver._link_to_company` and `pipeline.py`'s adviser-pair join logic. Both zero-overlap (0 of 1 adviser matches any company or person), row-level confirmed, disposed as source-coverage exclusions scoped explicitly to the current tracking-list universe.
- **EDGE-09 root cause found (unscoped follow-up, this session):** Re-tested `parse_proxy_fundamentals` against the actual bronze-captured Apple DEF 14A bytes (not a live re-fetch) — 5 rows, correct. Discovered all 23 DEF14A/DEFA14A attachments in dev silver belong to one company (Apple), invalidating 06-04's "Smaller Reporting Company" hypothesis. Found `sec_executive_record`/`sec_earnings_release` are 0 rows platform-wide. Traced this via live Step Functions execution history + CloudWatch logs (`load-history-oomtest-1783868231`) to `Stage1BPerFiling` silently skipping 100% of candidate filings (1822/1822, no errors logged). Root-caused to `_is_configured_parser_form` (`warehouse_orchestrator.py:1859-1861`), which gates the bulk artifact-fetch pipeline to ownership/ADV forms only — confirmed platform-wide (8-K: 104/266,634 filings have an attachment row; DEF14A-family: 23/52,200; 13F-HR: 0/48,877; 6-K: 0/108,863; NPORT-P: 0/104,787).
- **EDGE-11 disposition corrected:** the same gate that blocks EDGE-09 also blocks EDGE-11 — confirmed via `grep` that `refresh_filing_artifacts` has exactly two callers, and the standard bulk pipeline's caller is gated to exclude 13F-HR entirely. EDGE-11's previously-committed bronze-fetch fast-path fix is real and unit-tested, but unreachable in a standard bulk run; only reachable via the ungated `targeted_resync` single-accession path (which is how the original 61-filing test case, and Apple's 23 DEF14A attachments, got their data).
- **Task 2:** Confirmed `POPULATED_RELATIONSHIP_TYPES` correctly stays unchanged this phase — none of the 5 investigated types reached graph-verified-populated status. Updated the docstring comment to reflect Phase 6's actual findings. Re-ran `tests/mdm/test_cli_snowflake_graph.py` (18 tests, all passing) to confirm no regression from the comment-only change.
- **Task 3:** Wrote `06-PHASE-CLOSURE-LEDGER.md` with all 5 EDGE IDs, each in exactly one of three disposition categories (POPULATED / EXCLUDED / ROOT-CAUSED-FIX-DEFERRED — the third introduced explicitly to avoid misrepresenting EDGE-09/EDGE-11 as either populated or permanently excluded). Updated `REQUIREMENTS.md`'s checkboxes and Traceability table to match, correcting the premature `[x] Complete` status EDGE-09 and EDGE-11 had carried since the 2026-07-11 consolidation commit.

## Task Commits

1. **Task 1: EDGE-05/EDGE-06 D-04 zero-overlap closure** — `d375964` (completed prior session)
2. **EDGE-09/EDGE-11 shared root-cause discovery + disposition doc update** — `2cd0156`
3. **Task 2 (POPULATED_RELATIONSHIP_TYPES comment update) + Task 3 (closure ledger + REQUIREMENTS.md)** — this plan's final commit (see below)

## Files Created/Modified
- `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-PHASE-CLOSURE-LEDGER.md` — new, all 5 EDGE IDs disposed
- `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-04-EDGE09-EDGE11-DISPOSITION.md` — superseded EDGE-09's open item with a confirmed root cause; corrected EDGE-11's disposition
- `edgar_warehouse/mdm/snowflake_graph.py` — docstring comment updated (no tuple change)
- `.planning/workstreams/fix-pipelines/REQUIREMENTS.md` — EDGE-05/06/09/10/11 checkboxes + Traceability reconciled to the ledger

## Decisions Made
- Introduced a third disposition category (ROOT-CAUSED / FIX DEFERRED) for EDGE-09/EDGE-11 rather than forcing them into the plan's literal POPULATED/EXCLUDED binary — confirmed with the advisor before writing, since neither label would honestly describe "artifact present and fetchable, parser correct, but the bulk pipeline's selection gate never reaches this form type."
- Did not widen `_is_configured_parser_form` in this session — the fetch-volume/cost tradeoff (multiplying bulk SEC fetch volume by ~367k filings across 3 form types) is a scoped decision for the user, and the fix would not by itself advance either type to "populated" without the deploy+re-fetch+re-derive+sync+graph-count chain that is out of inline scope.
- Left `POPULATED_RELATIONSHIP_TYPES` unchanged — correctly a no-op given no type reached graph-verified-populated status this phase.

## Deviations from Plan

### Auto-fixed Issues

**1. [Unscoped follow-up, high value] EDGE-09's 06-04 "open item" status was resolved**
- **Found during:** Pre-Task-3 investigation, undertaken because live dev AWS access was available in this session (unlike 06-04's worktree executors) and resolving it would let the closure ledger avoid an awkward three-way disposition gap.
- **Issue:** 06-04 had left EDGE-09 honestly unresolved (parser worked on a live external fetch, but the actual dev-universe-specific cause was never tested against real captured bytes).
- **Fix:** Re-tested against real bronze content, traced through live Step Functions/CloudWatch evidence, root-caused to the same gate blocking EDGE-11. Consulted the advisor before committing to this reframing given it touches EDGE-11's already-recorded disposition too.
- **Files modified:** `06-04-EDGE09-EDGE11-DISPOSITION.md` (both sections updated with dated "2026-07-13 update" subsections, original content preserved and marked superseded rather than deleted)
- **Verification:** Live SQL against dev MDM Postgres/silver DuckDB (via `httpfs`), live Step Functions execution history, live CloudWatch logs — all cross-checked against each other (parser test, attachment-row query, execution-history state timing, CloudWatch completion metrics all agree).
- **Committed in:** `2cd0156`

**2. [Correction] EDGE-11's disposition needed updating, not just EDGE-09's**
- **Found during:** the same investigation — checking whether EDGE-11's already-committed fix was reachable.
- **Issue:** 06-04's EDGE-11 conclusion said "fix committed and unit-tested; live re-fetch is the concrete outstanding step" — implying the fix alone would resolve EDGE-11 once deployed. This was incomplete: the fix is unreachable via the standard bulk pipeline regardless of deployment, because the upstream gate never selects 13F-HR for artifact fetch at all.
- **Fix:** Added a "2026-07-13 update" section to EDGE-11's disposition clarifying the fix is necessary but not sufficient, and that it shares EDGE-09's root cause and deferred remediation.
- **Files modified:** `06-04-EDGE09-EDGE11-DISPOSITION.md`
- **Verification:** `grep -rn "refresh_filing_artifacts|fetch_filing_artifacts" edgar_warehouse/` — exactly 2 callers, confirmed live attachment coverage (0/48,877 for 13F-HR).
- **Committed in:** `2cd0156`

---

**Total deviations:** 2, both value-adding corrections to prior-plan documentation rather than scope creep on this plan's own 3 tasks — both were verified against live evidence before being written, and both were flagged to the advisor before committing to the reframing.
**Impact on plan:** All 3 of 06-06's own tasks completed as scoped. The unscoped EDGE-09 follow-up closed a real gap left open by 06-04, giving the closure ledger a fully evidenced disposition for all 5 phase relationship types instead of one honestly-open item.

## Issues Encountered
None this plan — no subagent dispatches (per explicit user instruction), no transient infra failures. AWS credential resolution required using the `sec_platform_deployer` profile (broader S3/read access than the default `edgartools-690`/`admin-user` identity, which returned 403/AccessDenied on the target buckets) — a one-time environment discovery, not a bug.

## Next Phase Readiness
- Phase 6 is closure-ready: all 3 of 06-06's tasks complete, all 5 EDGE IDs have exactly one evidenced disposition in `06-PHASE-CLOSURE-LEDGER.md`, REQUIREMENTS.md reconciled.
- **Concrete outstanding work for a future phase/session** (not this phase's scope): widen `_is_configured_parser_form` to cover Branch B's form families (8-K, DEF14A/DEFA14A/PRE14A, 13F-HR) — a scoped decision given the resulting SEC fetch-volume increase — then deploy, `--force` re-fetch, re-derive, sync-graph, and graph-count-verify EDGE-09 and EDGE-11.
- EDGE-05/EDGE-06 carry an explicit re-check trigger if the adviser universe ever grows beyond its current single entity.
- Still outstanding from earlier in this session (unrelated to 06-06 specifically): a PR from `claude/consolidate-workstreams` → `main` to land the OOM memory fix and artifact-throttle fixes, so CI's auto-deploy-on-push does not silently revert them again.

---
*Phase: 06-relationship-investigation-and-population*
*Completed: 2026-07-13*
