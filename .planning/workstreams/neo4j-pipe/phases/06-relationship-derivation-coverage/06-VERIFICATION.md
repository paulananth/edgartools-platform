---
phase: 06-relationship-derivation-coverage
verified: 2026-05-17T21:00:00Z
status: passed
score: 5/5
overrides_applied: 0
---

# Phase 6: Relationship Derivation Coverage Verification Report

**Phase Goal:** All graph-relevant relationships derivable from silver and resolved MDM entities are created as active MDM relationship rows without duplicates.
**Verified:** 2026-05-17T21:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `derive_relationships()` with no type filter inserts zero rows on a second run for all 6 types (IS_INSIDER, HOLDS, ISSUED_BY, MANAGES_FUND, IS_ENTITY_OF, IS_PERSON_OF) | VERIFIED | `test_all_six_types_idempotent` PASSED; asserts `second[rt]["inserted"] == 0` for all 6 types via loop |
| 2 | Summary dict exposes `skipped_corporate`, `skipped_unresolved_source`, `skipped_unresolved_target`, `skipped_existing` alongside `skipped` for every type | VERIFIED | `derive_relationships()` lines 227-238: 9-key dict with all 4 sub-counters present in every type's entry; counter grep returns 18 non-comment hits |
| 3 | `skipped == skipped_corporate + skipped_unresolved_source + skipped_unresolved_target + skipped_existing` holds exactly for every type and every run | VERIFIED | Mechanically enforced: `"skipped"` is computed as the literal arithmetic sum expression at lines 230-231 inside the dict literal, not from a returned value; `test_all_six_types_idempotent` asserts the invariant for all 6 types on second run |
| 4 | Structured `mdm_relationship_skip` JSON-line events emitted to stderr for IS_INSIDER and HOLDS skips only (all 4 reason codes: corporate, unresolved_source, unresolved_target, existing) | VERIFIED | 8 emit calls confirmed; line numbers 282, 293, 305, 326 fall in `_derive_is_insider` (262-336); lines 362, 373, 385, 412 fall in `_derive_holds` (337-422); zero emit calls in entity-only derivers (423+) |
| 5 | A single MANAGES_FUND row and a single ISSUED_BY row are inserted when fixture_world contains the required MdmFund and MdmSecurity instances | VERIFIED | `test_writes_manages_fund_relationship` PASSED (inserted==1); `test_writes_issued_by_relationship` PASSED (inserted==1); fixture_world seeded with MdmFund (adviser_entity_id=firm_adviser_id) and MdmSecurity (issuer_entity_id=issuer_company_id) |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/mdm/test_pipeline_relationships.py` | RED tests for MANAGES_FUND, ISSUED_BY, D-02 counter shape, and D-04 all-types idempotency; GREEN after Task 3 | VERIFIED | 3 new test methods present; MdmFund imported; fixture_world returns `fund_entity_id` and `security_entity_id`; all 24 tests PASS |
| `edgar_warehouse/mdm/pipeline.py` | Broken-down skip counters (D-02), inline stderr skip events (D-03) | VERIFIED | 5-tuple returns from all 6 `_derive_*` methods; 9-key summary dict; 8 D-03 emit calls (4 per method × IS_INSIDER + HOLDS); `json`, `sys`, `datetime` imports present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/mdm/test_pipeline_relationships.py` | `edgar_warehouse/mdm/pipeline.py` | `derive_relationships()` summary dict assertions checking `skipped_corporate`, `skipped_unresolved_source`, `skipped_unresolved_target`, `skipped_existing` | WIRED | `test_writes_manages_fund_relationship`, `test_writes_issued_by_relationship`, and `test_all_six_types_idempotent` all assert on the sub-counter keys; keys exist in dict; tests PASS |
| `edgar_warehouse/mdm/pipeline.py` | `sys.stderr` | inline `print(json.dumps({...}), file=sys.stderr, flush=True)` with `event: mdm_relationship_skip` | WIRED | 8 emit calls verified at correct line numbers; `json`, `sys`, `datetime/timezone` imported; no import from `sec_client.py` |
| `edgar_warehouse/mdm/pipeline.py` | `edgar_warehouse/mdm/pipeline.py (PipelineStats)` | `relationship_counts_by_type` stores summary dict verbatim | WIRED | `derive_relationships()` returns summary dict with all 9 keys; callers receive the dict directly |

### Data-Flow Trace (Level 4)

Not applicable — this phase modifies test coverage and diagnostic instrumentation, not user-facing rendering components. The data flow is: silver rows → `_derive_*` method → skip/insert counters → summary dict → test assertions. This is covered by the test suite (all 24 PASS).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 24 relationship tests pass | `uv run pytest tests/mdm/test_pipeline_relationships.py -v` | 24 passed in 12.70s | PASS |
| Full MDM suite — no regressions | `uv run pytest tests/mdm/ -v` | 176 passed, 4 errors (NEO4J_URI environment errors in test_graph.py — pre-existing, unrelated) | PASS |
| 3 new test methods exist | `grep -c 'test_writes_manages_fund_relationship\|test_writes_issued_by_relationship\|test_all_six_types_idempotent' tests/mdm/test_pipeline_relationships.py` | 3 | PASS |
| `skipped_corporate` appears 18 times (>= 6 expected) | `grep -v comment \| grep -c 'skipped_corporate'` | 18 | PASS |
| D-03 emit calls: exactly 8 | `grep -v comment \| grep -c 'mdm_relationship_skip'` | 8 | PASS |
| No old 2-tuple assignments remain | `grep -v comment \| grep -c 'inserted, skipped = '` | 0 | PASS |
| D-03 scope: emit calls only in IS_INSIDER and HOLDS | `grep -n 'mdm_relationship_skip'` lines 282, 293, 305, 326, 362, 373, 385, 412 | All 8 within ranges 262-336 (_derive_is_insider) and 337-422 (_derive_holds) | PASS |
| No import from sec_client | `grep -c 'from edgar_warehouse.infrastructure.sec_client' pipeline.py` | 0 | PASS |
| `skipped` backward-compat mechanically enforced in derive_relationships() | Read pipeline.py lines 227-238 | `"skipped"` = literal arithmetic sum at construction; not from a returned variable | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| REL-01 | 06-01-PLAN.md | IS_INSIDER rows cover non-corporate Forms 3/4/5 reporting-owner to issuer pairs | SATISFIED | `test_writes_is_insider_for_natural_persons` PASSED; `test_skips_corporate_beneficial_owner` PASSED; `skipped_corporate` counter present and enforced |
| REL-02 | 06-01-PLAN.md | HOLDS and ISSUED_BY rows cover ownership security relationships where owner, security, and issuer resolve | SATISFIED | `test_writes_holds_from_non_derivative_transactions` PASSED; `test_writes_issued_by_relationship` PASSED; both in `test_all_six_types_idempotent` first-run sanity assertions |
| REL-03 | 06-01-PLAN.md | MANAGES_FUND, IS_ENTITY_OF, and IS_PERSON_OF rows cover adviser/fund/company/person relationships | SATISFIED | `test_writes_manages_fund_relationship` PASSED; `test_writes_is_entity_of` PASSED; `test_writes_is_person_of` PASSED; all three in first-run sanity assertions of idempotency test |
| REL-04 | 06-01-PLAN.md | Re-running relationship derivation against unchanged data inserts zero new active duplicate rows | SATISFIED | `test_all_six_types_idempotent` PASSED; asserts `second[rt]["inserted"] == 0` for all 6 types; D-02 backward-compat invariant also asserted on second run |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

No TODOs, FIXMEs, placeholder returns, or stub patterns found in the modified files.

### Human Verification Required

None. All success criteria are mechanically verifiable via grep counts, line-number ranges, and pytest output.

### Gaps Summary

No gaps. All 5 must-have truths verified. All 2 required artifacts substantive and wired. All 4 key links confirmed. All 4 requirements satisfied.

---

_Verified: 2026-05-17T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
