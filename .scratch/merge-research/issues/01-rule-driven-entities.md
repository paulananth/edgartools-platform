# Rule-driven entity merge research

Type: research
Status: open

Question: Can one rule-produced row use a shared merge for Company, Person and Security, and what remains hard-coded?

- [x] Trace the current worker and rule-produced record contract; inspected the pinned worker, preparation and assertion constructor (2026-11-13 07:04 ET).
- [x] Separate configured entity policy from fixed engine behavior and concrete assumptions; inspected rules, shared Rust functions and LEI-specific matching (2026-11-13 07:04 ET).
- [x] Record source citations, existing test coverage and recommendation in docs/research; tests identified as inspected, not executed (2026-11-13 07:04 ET).
- [x] Review Standards, Spec and GoF; no substantive findings, ticket metadata and title clarified; documentation checks 107 passed in 0.51s (2026-11-13 07:04 ET).
- [ ] Publish the research in a PR.
- [x] Learning → skill: none; the findings follow the existing shared-engine and configured-policy contract (2026-11-13 07:04 ET).
