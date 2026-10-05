# Company main reader retirement qualification

Continue the full installed Rules creator/orchestration and complete parser-retirement goal. Parent PR #827; local qualification only, no SEC requests or source activation.

- [x] Inspect executable consumers and existing loader/source history; apply GoF review. — 2026-10-05 08:14 ET; source/loader history and runtime consumers inspected; retain generic function/enum design.
- [x] Audit exact Company, filing and business-address tables and refusal decisions across a finite input-shape matrix. — 2026-10-05 08:14 ET; initial 449 cases found 50 differences; resolved audit matches all 449, including 54 refusals; four deliberate faults detected; 76 focused Python tests passed.
- [x] Resolve the 50 demonstrated main-document configuration gaps; preserve independent historical oracles. — 2026-10-05 08:14 ET; generic document assertions, business-object iteration and explicit place conversion; 3 native assertion tests passed.
- [x] Remove unused runtime landing API and loader modules after exhaustive executable-consumer inspection; preserve frozen test oracles and verify installed package absence. — 2026-10-05 08:28 ET; consumer inspection, 826 post-removal tests, 7 import guard tests; committed installed snapshot 26c81ec8 proves both modules absent and main/page restricted PostgreSQL 16 modes pass (2 passed/no skips, 157.69 seconds).
- [ ] Resolve remaining active MDM classification/preparation/publication contracts before retiring their executable callers.
- [x] Qualify pinned captured bytes and installed PostgreSQL 16 worker/verifier behavior; review and full CI; commit/push/create PR. — 2026-10-05 08:30 ET; captured 1,000 mains/107,197 filings; final installed 2 passed/no skips157.69s;90 Rust; reviews closed; PR #828; CI37309510766 passed all suites and aggregate gate on26c81ec8. Final evidence commit must pass CI before readiness.
- [ ] Complete census/cascade/provenance, GLEIF/configured acquisition, full installed population/recovery and all old parser deletion in the parent goal.

GoF review: history shows entity classification, country codes and configured reading additions. Retain the existing function/enum design; no new class hierarchy is justified. The measured contract gaps determine the next implementation.

## Scoped review

Independent Standards/GoF review found no scoped blockers or justified pattern refactor. Independent Spec review found no scoped findings. Physical replay passed; final installed/full CI evidence remains pending. This change resolves a finite accepted/refused shape matrix, not universal arbitrary-input equivalence. The signed numeric, Unicode, byte and record bounds of the native reader remain explicit.

## Runtime retirement evidence

An exhaustive runtime/package consumer search found no executable references to SilverLandingStore. Its only loader consumer was its own unused stage_submission method. All four runtime source files are removed. Frozen implementations under tests/support preserve independent historical parity and rollback-fixture tests; installed wheels do not package those archives. No wrapper or runtime fallback replaces the retired APIs. Active mdm/clean/company_source preparation and provenance remain unfinished.

Post-removal unit, architecture and affected engine tests: 826 passed/no skips in 150.93 seconds. Independent Standards review identified incomplete future import detection; the guard now resolves absolute module aliases and relative imports, and all six deliberate reintroduction cases fail the retirement boundary (7 guard tests pass). Reviewer confirmed closure.

The configured main read/verify replay passed 1,000 receipt-pinned captures, 1,000 Company rows and 107,197 filing rows in 293.038 seconds. Its native binary and contract digests are in captured-main-qualification.json. 90 full Rust tests passed. Before runtime removal, installed main/page modes passed on restricted PostgreSQL 16 roles (2 passed/no skips, 174.04 seconds); final installed package absence verification is required.

## Final installed snapshot

At 26c81ec8, the installed bundle has neither edgar_warehouse.loaders nor edgar_warehouse.silver_landing_store (isolated importlib.find_spec checks). Both Company main and pagination read/verify trials passed on restricted PostgreSQL 16 roles: 2 passed/no skips in 157.69 seconds. Independent review findings are closed. PR #828 remains draft until the final evidence commit passes all CI gates; implementation CI 37309510766 passed on26c81ec8.
