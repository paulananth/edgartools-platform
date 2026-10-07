# GLEIF field mapping review

Independent read-only reviews of 4bf0e8b7 against f56f8548.

## Specification

Zero scoped blockers. Bounded primitives, frozen reading, cache keys and selective runtime evaluation match the ticket. Sample evidence excludes complete EOF, semantic corpus and installed mastering. Remaining module retirement/population/replay/recovery gates stay open.

## Standards

One documented finding: unselected expressions were removed before contract validation, contrary to READING.md. Fixed by cached compilation of the complete immutable reading before selective runtime projection. Regression rejects malformed unused matching; all 146 affected cases and 3,000 captured comparisons passed after the fix. Full native suite passed 139 cases. Independent standards follow-up confirmed the fix at be01b22e; both reviewers found no new scoped blocker through 04737abf. Final implementation CI 37698204328 passed every job and gate at df6e3232.

GoF: retain interpreter/plain functions; no warranted class hierarchy or other refactor. The frozen recipe duplication has a checked equality invariant.

## Runtime dependency audit

mdm.merge previously omitted the newly used configured mapping/native engine dependencies. Added those dependencies to its runtime fingerprint and five deliberate-fault regressions; all 44 field/runtime cases passed. Five real restricted-role PG16 worker/mastering cases passed in 53.06s. Independent standards follow-up confirmed dependency coverage and found no scoped blocker. Final implementation CI 37698204328 passed at df6e3232; counts and log hash are in ci-proof.json.
