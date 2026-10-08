# Retire executable Company address derivation

Parent goal: self-sustaining skills and Rules creator, parsing/MDM orchestration, complete old-parser retirement. Based on merged PR #858; synchronization onto current main is pending. Local qualification only; no SEC requests, deployment or activation.

- [x] Create isolated Codex branch/tree and inspect Company preparation/history. GoF: c9158d57 changed state/country semantics; configured main/address reading already represents it. Reuse generic native projection; no new class hierarchy (2026-10-07 19:23 ET).
- [x] Freeze landed-address projection and place table in bundled Rules; remove production business_address and execute generic project_record in the preparation/census collector. 64 affected tests passed in 7.32s, including every pinned place-code variant (2026-10-08 06:07 ET).
- [ ] Keep a historical oracle exclusively in test support; qualify every pinned place code, malformed/missing values and exact captured address outcomes against it. Preserve distinct source parser, identity and release checks.
- [ ] Verify affected Company preparation/census tests and installed restricted PostgreSQL publication/recovery; independent review and full CI; publish separate reviewable PR.
- [ ] Complete Company preparation/census/provenance and GLEIF semantic/release replacement, frozen-version record-mapping retirement, installed 6,414 Company / 3,052 CIK+LEI replay/recovery and parent L3–L8. Full goal remains incomplete.

- [x] Initial final-helper qualifier: 1,000 receipt-authenticated raw and landed addresses matched historical outputs in 80.1s; before/after pins include extractor, native/helper, worker and actual published reference data (2026-10-08 06:07 ET).

- [x] Address review findings identified and implementation corrected: missing extractor/worker pins added, and installed test now feeds actual _business_addresses output into SEC assertions/publication. Review agents hit their usage limit before final confirmation; final independent review remains open (2026-10-08 06:07 ET).
