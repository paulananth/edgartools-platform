# Fix PersonResolver's skip-if-unchanged gap

Type: task
Status: resolved
Blocked by: 01

## Question

Ticket 01 confirmed `PersonResolver` is the one live resolver missing the
skip-if-unchanged fast path `CompanyResolver` and `SecurityResolver`
already have. `run_persons()` has no resumable ledger, so every `mdm run`
restart re-selects the full `sec_ownership_reporting_owner` universe and
re-stages every row from scratch. Port the fix.

## Answer

Reproduced first, per `/diagnosing-bugs` discipline: a throwaway two-call
test against a real SQLite-backed `MDMPipeline` showed
`mdm_entity_attribute_stage` row count doubling (6 → 12) on an unchanged
second `run_persons()` call. Confirmed via `git stash` that the test fails
red without the fix and passes green with it.

Fix mirrors `SecurityResolver.resolve_one`'s pattern exactly:
`edgar_warehouse/mdm/resolvers/person.py`'s `resolve_one` now computes
`content_hash(attrs)` (covering `owner_cik`, `canonical_name`,
`issuer_cik`, `primary_role`) before doing any candidate lookup, checks
`_skip_if_unchanged`, and returns early with `MatchAction.SKIPPED_UNCHANGED`
on a hash match. `_register_source` now passes `source_content_hash`.

One deliberate departure from a naive port: `issuer_cik` is included in
the hash even though `PERSON_FIELDS` never stages it as a golden value —
it's a `FuzzyNameMatcher` match-context field for `owner_cik`-less rows
(`_build_pipeline`'s `context_fields=("issuer_cik",)`), so a row whose
issuer context changes between runs must still be reprocessed, not
skipped. Covered by
`test_issuer_cik_change_is_not_skipped`.

5 new tests in `tests/mdm/test_run_persons_skip_unchanged.py`, mirroring
`test_run_securities_skip_unchanged.py`'s structure and test count:
`test_second_run_over_unchanged_data_skips_every_row`,
`test_second_run_reuses_entity_id_on_skip`,
`test_issuer_cik_change_is_not_skipped`, plus (added after a `/code-review`
Standards pass flagged their absence as a real parity gap against the
security/company sibling files, not a judgement call)
`test_skip_if_unchanged_returns_none_when_no_prior_match_exists` and
`test_skip_if_unchanged_returns_none_on_hash_mismatch`, direct-call
coverage of the shared `_skip_if_unchanged` base method. All 5 pass; the
first fails red without the fix (verified via `git stash`).

A parallel `/code-review` Spec pass confirmed all 5 pattern requirements
(hash placement, hash coverage including `issuer_cik`, early-return shape,
`source_content_hash` pass-through, and genuine red/green test coverage)
were satisfied faithfully, with no scope creep. It also noted
`test_second_run_reuses_entity_id_on_skip` doesn't actually differentiate
pre-fix from post-fix behavior (CIK-exact matching alone would produce the
same entity_id either way) -- true, but identical to the accepted
precedent already in `test_run_securities_skip_unchanged.py`, not a new
gap introduced here.

Full `tests/mdm/` suite: 538 passed. Full repo suite: 2308 passed, 4
skipped, only the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures (same known baseline as
every prior entry in this session's history).
