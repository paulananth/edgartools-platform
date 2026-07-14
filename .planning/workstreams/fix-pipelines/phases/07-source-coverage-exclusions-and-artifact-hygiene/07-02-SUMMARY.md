---
phase: 07
plan: 02
subsystem: mdm-relationship-coverage-manifest
tags: [mdm, coverage, exclusions, verification]
requires: [07-01]
provides: [relationship-coverage-manifest, edge07-edge08-disposition, exhaustive-named-checks]
affects: [07-03, 07-04, 07-05, snowflake_graph.verify_graph]
key-files:
  created:
    - edgar_warehouse/mdm/migrations/007_relationship_coverage.sql
    - tests/mdm/test_relationship_coverage.py
  modified:
    - edgar_warehouse/mdm/coverage.py
    - edgar_warehouse/mdm/database.py
    - edgar_warehouse/mdm/migrations/runtime.py
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_runtime_ops.py
    - .planning/workstreams/fix-pipelines/REQUIREMENTS.md
    - .planning/workstreams/fix-pipelines/phases/07-source-coverage-exclusions-and-artifact-hygiene/07-01-SUMMARY.md
key-decisions:
  - EDGE-07's evidence was independently re-verified live rather than trusted from the cited
    (nonexistent) claude-mdm-source-recovery/FINDINGS.md: sec_company_filing's 30 ADV-family
    filings in the tracked universe are all ADV-E/ADV-NR (11 CIKs), never a primary ADV/ADV-A
    entry; confirmed against live SEC EDGAR submissions.json for 3 of those CIKs. Corrected
    root cause is "Form ADV Part 1A/Schedule D is an IARD artifact, not an EDGAR one" --
    structurally unobtainable, not a paper-filing technicality as the stale doc trail implied.
  - EDGE-09/EDGE-11 map to valid_zero, not excluded -- the plan's status enum is
    {populated, valid_zero, excluded} with no third bucket, and valid_zero's definition
    ("proven-zero-for-now, recomputed every generation, not necessarily permanent") is exactly
    Phase 6's "ROOT-CAUSED / FIX DEFERRED" disposition. Fingerprinted directly against
    _is_configured_parser_form's own governing form sets (imported, not restated) so the
    fingerprint cannot silently drift out of sync with the real gate.
  - snowflake_graph.py's _named_relationship_parity_checks takes relationship_coverage as an
    optional parameter (default None = unchanged pre-07-02 behavior, scoped to
    POPULATED_RELATIONSHIP_TYPES only) rather than replacing the function outright. Wiring a
    live coverage manifest into the actual `mdm verify-graph` CLI path requires a second
    (Postgres) connection that command doesn't open today -- out of this plan's file scope
    (cli.py is not in files_modified) and deferred to whichever later plan builds the real
    generation coordinator (07-03/07-04/07-05).
  - Found and corrected a real overclaim in 07-01-SUMMARY.md while updating REQUIREMENTS.md's
    traceability table: RTEMP-01 and RLINE-01 were marked fully complete, but RTEMP-01's
    Neo4j-sync half and RLINE-01's entity-merge-remapping half were never implemented. Both
    downgraded to partial in REQUIREMENTS.md and 07-01-SUMMARY.md, with an explicit correction
    note rather than silently editing the claim away.
requirements-completed: [EDGE-07, EDGE-08, RCOV-01, RCOV-02]
completed: 2026-07-14
---

# Phase 7 Plan 02: Exhaustive Relationship Coverage And Exclusion Policy

## Results

- New `mdm_relationship_coverage` table (one record per generation/relationship-type),
  status restricted to `populated|valid_zero|excluded`, with `expected_edge_count`,
  `evidence_category`, `evidence_query_version`, `evaluated_at`, `population_fingerprint`,
  `review_trigger`. Additive migration (`007_relationship_coverage.sql`).
- `coverage.py` gained a full classification layer:
  - `compute_edge05_is_entity_of_coverage`/`compute_edge06_is_person_of_coverage` (D-04
    zero-overlap, reproducing Phase 6's exact join logic independently).
  - `compute_edge07_manages_fund_coverage` (`source_unavailable`, re-verified live).
  - `compute_edge08_has_parent_company_coverage` (`capability_not_implemented`, confirmed via
    `resolvers/company.py` code reading -- `_parent_company_entity_id` always returns `None`).
  - `compute_edge10_audited_by_coverage` (`structural_api_limitation`, from 06-05's evidence).
  - `compute_deferred_fix_coverage` (EDGE-09/EDGE-11 -> `valid_zero`, fingerprinted on
    `_is_configured_parser_form`'s actual governing form sets).
  - `compute_relationship_coverage_manifest`: exactly one record per active
    `MdmRelationshipType` (all 11), raising `KeyError` for any unclassified type.
  - `verify_relationship_coverage_manifest`: fail-closed on missing types, contradictory
    duplicate statuses, zero-count populated types, nonzero-count excluded/valid-zero types,
    and stale fingerprints.
- `snowflake_graph.py`'s `_named_relationship_parity_checks` gained an optional
  `relationship_coverage` parameter: when supplied, evaluates exhaustively over every type in
  the map (populated types must be at parity; excluded/valid-zero types must have zero live
  rows on both sides -- nonzero is now a hard failure, not silence). Default (`None`) preserves
  exact pre-07-02 behavior (`POPULATED_RELATIONSHIP_TYPES`-only scoping) -- zero regressions in
  the 18 pre-existing `test_cli_snowflake_graph.py` tests.

## Live Re-verification (not just re-reading prior docs)

EDGE-07's previously-cited evidence file (`claude-mdm-source-recovery/FINDINGS.md`) does not
exist -- only an open-investigation `CLAUDE-INSTRUCTIONS.md` remains in that directory, reading
as an unresolved next step, not a closed dead end. Rather than encode an unverified claim into a
system whose entire threat model is "exclusions become permanent silent waivers," re-verified
live:
- `sec_company_filing` (silver DuckDB, `sec_platform_deployer` AWS profile): 30 ADV-family
  filings across 11 CIKs, all `ADV-E` (22) or `ADV-NR` (8) -- never a primary `ADV`/`ADV-A`.
- Live SEC EDGAR `submissions.json` for 3 of those CIKs (749044, 1040410, 1302739): each
  CIK's *entire* filing history contains only `ADV-E`/`13F-HR`/`13F-HR/A`/`N-PX` -- no primary
  ADV entry ever.
- Conclusion: Form ADV Part 1A/Schedule D (the document that would carry private-fund
  management data) is filed through IARD, not EDGAR, for this population -- a structural,
  non-EDGAR-artifact gap. This refines (does not contradict) the standing "unobtainable"
  conclusion, but corrects the imprecise "paper filing" framing and grounds it in fresh,
  reproducible evidence rather than a broken doc citation.

## Deviations from Plan

**[Rule 3 - Scope] cli.py not touched.** The plan's `files_modified` list (coverage.py,
database.py, migrations.py, snowflake_graph.py, test file) does not include `cli.py`, and
`mdm verify-graph`'s handler only opens a Snowflake connection (no MDM Postgres session),
so it cannot compute a live coverage manifest itself. Built the capability
(`relationship_coverage` param, backward-compatible default) without wiring it into the live
CLI path -- consistent with the plan's own scope and 07-CONTEXT.md's plan-by-plan structure
(a real generation coordinator doesn't exist until 07-03+).

**[Rule 1 - Bug, caught while updating REQUIREMENTS.md] 07-01 overclaimed RTEMP-01 and
RLINE-01.** See `07-01-SUMMARY.md`'s correction note. Both requirements were listed complete
in 07-01 but each had an unimplemented half (Neo4j sync; entity-merge remapping). Downgraded to
partial in both `REQUIREMENTS.md` and `07-01-SUMMARY.md` rather than silently correcting the
claim -- this session's own error, caught and fixed inline per the project's 5-whys discipline.

## Verification

```text
uv run pytest tests/mdm/test_relationship_coverage.py -k 'fingerprint or exclusion' -q
11 passed

uv run pytest tests/mdm/test_relationship_coverage.py -q
27 passed

uv run pytest tests/mdm/test_relationship_coverage.py tests/mdm/test_snowflake_graph_migration.py -q
39 passed

uv run pytest tests/ -q -x --ignore=tests/architecture/test_load_history_state_machine.py
636 passed
```

(The excluded architecture test is pre-existing, unrelated, verified failing identically with
this plan's changes stashed out -- see 07-01-SUMMARY.md.)

## Self-Check: PASSED

EDGE-07, EDGE-08, RCOV-01, RCOV-02 complete. Plan 07-03 (transactional MDM publication queue,
watermarks, lifecycle states, freshness SLO, alerts) may begin. RTEMP-01's Neo4j-sync gap and
RLINE-01's entity-merge-remapping gap remain open (not blocking 07-03, but should be picked up
by whichever plan builds the real generation/sync coordinator).
