# Retire executable Company address derivation

Parent goal: self-sustaining skills and Rules creator, parsing/MDM orchestration, complete old-parser retirement. Based on merged PR #858; rebased onto current main 4a673ec6. Local qualification only; no SEC requests, deployment or activation.

- [x] Create isolated Codex branch/tree and inspect Company preparation/history. GoF: c9158d57 changed state/country semantics; configured main/address reading already represents it. Reuse generic native projection; no new class hierarchy (2026-10-07 19:23 ET).
- [x] Freeze landed-address projection and place table in bundled Rules; remove production business_address and execute generic project_record in the preparation/census collector. 64 affected tests passed in 7.32s, including every pinned place-code variant (2026-10-08 06:07 ET).
- [x] Historical oracle is exclusively in unshipped test support; all pinned place-code variants and malformed JSON values matched. 721 MDM/projection cases passed before rebase; final rebased capture qualifier matched 1,000 raw/landed addresses in 90.888s with before/after extractor/worker/native/helper/Rules/published-reference pins (2026-10-08 06:10 ET).
- [x] Post-rebase affected suite passed 720 cases in 34.17s; three installed cases passed with restricted PG16 publication/recovery; independent reviews found zero scoped blockers; PR #864 published. Full CI 37762135297 passed every job/gate at 96dd4997: 572 unit, 258 architecture, 607 MDM, 295 integration + one expected xfail, 649 engine and 139 native; no prerequisite skips. Final evidence-only head requires its own CI before readiness (2026-10-08 06:22 ET).
- [ ] Complete Company preparation/census/provenance and GLEIF semantic/release replacement, frozen-version record-mapping retirement, installed 6,414 Company / 3,052 CIK+LEI replay/recovery and parent L3–L8. Full goal remains incomplete.

- [x] Initial final-helper qualifier: 1,000 receipt-authenticated raw and landed addresses matched historical outputs in 80.1s; before/after pins include extractor, native/helper, worker and actual published reference data (2026-10-08 06:07 ET).

- [x] Address review findings identified and implementation corrected: missing extractor/worker pins added, and installed test now feeds actual _business_addresses output into SEC assertions/publication. Review agents initially hit their usage limit; final confirmation was completed subsequently (recorded below) (2026-10-08 06:07 ET).

- [x] Final independent specification and standards/GoF reviews at a0df7857 confirmed prior gaps fixed and zero remaining scoped blockers; installed collector publication evidence remains pending (2026-10-08 06:10 ET).

- [x] Installed committed bundle a0df7857 exercised actual Parquet address collector; its native-derived addresses became published SEC assertions. Three installed cases passed, zero skips, 208.40s, including restricted PG16, lost-ACK retry, duplicate replay and denied writes. Four fixture entities; full population remains unqualified (2026-10-08 06:14 ET).

- [x] Post-rebase scan found removed legacy sec-place-codes.yaml referenced by the new test; migrated that test to pinned_reference, preserving all code variants. Full affected suite/CI must confirm (2026-10-08 06:14 ET).

- [x] Deliberate in-process recipe fault set country to ZZ; existing preparation test failed exactly on country ZZ versus US. Repository files were not modified; recorded in ci-proof.json (2026-10-08 06:22 ET).

- [x] Claude finished the overlapping test-file work in merged #862 (4840c6ba), incorporated before the post-rebase fix; live overlap guard passes (2026-10-08 06:22 ET).
