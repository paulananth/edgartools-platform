# Retire executable Company address derivation

Parent goal: self-sustaining skills and Rules creator, parsing/MDM orchestration, complete old-parser retirement. Based on merged PR #858; rebased onto current main 4a673ec6. Local qualification only; no SEC requests, deployment or activation.

- [x] Create isolated Codex branch/tree and inspect Company preparation/history. GoF: c9158d57 changed state/country semantics; configured main/address reading already represents it. Reuse generic native projection; no new class hierarchy (2026-10-07 19:23 ET).
- [x] Freeze landed-address projection and place table in bundled Rules; remove production business_address and execute generic project_record in the preparation/census collector. 64 affected tests passed in 7.32s, including every pinned place-code variant (2026-10-08 06:07 ET).
- [x] Historical oracle is exclusively in unshipped test support; all pinned place-code variants and malformed JSON values matched. 721 MDM/projection cases passed before rebase; final rebased capture qualifier matched 1,000 raw/landed addresses in 90.888s with before/after extractor/worker/native/helper/Rules/published-reference pins (2026-10-08 06:10 ET).
- [ ] Verify affected Company preparation/census tests and installed restricted PostgreSQL publication/recovery; independent review and full CI; publish separate reviewable PR.
- [ ] Complete Company preparation/census/provenance and GLEIF semantic/release replacement, frozen-version record-mapping retirement, installed 6,414 Company / 3,052 CIK+LEI replay/recovery and parent L3–L8. Full goal remains incomplete.

- [x] Initial final-helper qualifier: 1,000 receipt-authenticated raw and landed addresses matched historical outputs in 80.1s; before/after pins include extractor, native/helper, worker and actual published reference data (2026-10-08 06:07 ET).

- [x] Address review findings identified and implementation corrected: missing extractor/worker pins added, and installed test now feeds actual _business_addresses output into SEC assertions/publication. Review agents hit their usage limit before final confirmation; final independent review remains open (2026-10-08 06:07 ET).

- [x] Final independent specification and standards/GoF reviews at a0df7857 confirmed prior gaps fixed and zero remaining scoped blockers; installed collector publication evidence remains pending (2026-10-08 06:10 ET).

- [x] Installed committed bundle a0df7857 exercised actual Parquet address collector; its native-derived addresses became published SEC assertions. Three installed cases passed, zero skips, 208.40s, including restricted PG16, lost-ACK retry, duplicate replay and denied writes. Four fixture entities; full population remains unqualified (2026-10-08 06:14 ET).

- [x] Post-rebase scan found removed legacy sec-place-codes.yaml referenced by the new test; migrated that test to pinned_reference, preserving all code variants. Full affected suite/CI must confirm (2026-10-08 06:14 ET).
