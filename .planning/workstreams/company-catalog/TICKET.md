# Configured Company ticker catalog

Parent goal: self-sustaining installed Rules/parsing/MDM orchestration and complete old-parser retirement. Base PR #822 e5c25468; local qualification only.

- [x] Inspect retained ticker parsing, pinned capture shape and GoF change history; demonstrate any grammar gap. — existing each:data emitted null CIK and matrix declaration was rejected; historical parser/landing changes inspected; 2026-10-05 07:16 ET.
- [x] Add generic configuration support only for a demonstrated gap; preserve existing readers and budgets. — four matrix native tests and full Rust suite passed; 2026-10-05 07:16 ET.
- [ ] Package a catalog contract and prove exact typed capture rows, catalog rank and Company ticker grouping through verified receipts.
- [x] Verify malformed headers/rows, full row bounds and selection; keep unqualified legacy shape handling explicit. — native header/row/selection refusal tests and nine Company catalog cases passed; 2026-10-05 07:16 ET.
- [ ] Verify installed bundle, independent review and full CI; commit/push/create a reviewable PR.
- [ ] Complete Company census/cascade, producer provenance, acquisition and adapter replacement, GLEIF, installed population/replay and all old-parser deletion in the parent goal.

GoF: existing configured iteration is a function-based parsing boundary. History shows parallel layout/coercion changes; header-driven arrays are a measured missing layout. A generic matrix iterator is sufficient; a provider loader or class hierarchy would add indirection without reducing current work.

Retirement remains incomplete. This strict draft refuses malformed rows that legacy parsing skips/truncates, and does not yet cover the dictionary ticker catalog. Existing runtime callers are retained until those gaps and governance/provenance are qualified.
