# Configured Company ticker catalog

Parent goal: self-sustaining installed Rules/parsing/MDM orchestration and complete old-parser retirement. Base PR #822 e5c25468; local qualification only.

- [x] Inspect retained ticker parsing, pinned capture shape and GoF change history; demonstrate any grammar gap. — existing each:data emitted null CIK and matrix declaration was rejected; historical parser/landing changes inspected; 2026-10-05 07:16 ET.
- [x] Add generic configuration support only for a demonstrated gap; preserve existing readers and budgets. — four matrix native tests and full Rust suite passed; 2026-10-05 07:16 ET.
- [x] Package a catalog contract and prove exact typed capture rows, catalog rank and Company ticker grouping through verified receipts. — qualification.json: 10,391 exact typed catalog rows, five captured Companies, independently verified read/combine/prepare and ranked distinct tickers; final replay 24.818 seconds; 2026-10-05 07:20 ET.
- [x] Verify malformed headers/rows, full row bounds and selection; keep unqualified legacy shape handling explicit. — native header/row/selection refusal tests and nine Company catalog cases passed; 2026-10-05 07:16 ET.
- [x] Verify installed bundle, independent review and full CI; commit/push/create a reviewable PR. — installed trial and both reviews passed; rebased CI 37302410215 passed all suites/gate (1,741 Python, 82 Rust, one existing xfail, no skips); PR #826 created; 2026-10-05 07:25 ET.
- [ ] Complete Company census/cascade, producer provenance, acquisition and adapter replacement, GLEIF, installed population/replay and all old-parser deletion in the parent goal.

GoF: existing configured iteration is a function-based parsing boundary. History shows parallel layout/coercion changes; header-driven arrays are a measured missing layout. A generic matrix iterator is sufficient; a provider loader or class hierarchy would add indirection without reducing current work.

Retirement remains incomplete. This strict draft refuses malformed rows that legacy parsing skips/truncates, and does not yet cover the dictionary ticker catalog. Existing runtime callers are retained until those gaps and governance/provenance are qualified.

## Review and installed evidence

Independent Standards/GoF review found no scoped violations. Spec review found synthesized rows lacked JSON key order for whole-row Python text; fixed at 2e26640e with a native regression, reviewer confirmed closure. Full Rust suite passes, including five new matrix cases. The corrected binding passes 69 focused cases and the final capture replay.

Installed Company catalog trial passed with restricted PostgreSQL 16 worker/verifier roles in 176.73 seconds at 89188cc9. The scalar catalog contract is unchanged by the header-order correction; final CI must exercise the installed trial at the final head before readiness. Full retirement remains incomplete.

Final rebased implementation head c3367b27 passed installed bundle coverage in CI 37302410215. This checklist-only commit requires its final-head CI before PR readiness. Source, contract and test bytes remain unchanged by the rebase and this evidence update. Parent retirement item stays unchecked.
