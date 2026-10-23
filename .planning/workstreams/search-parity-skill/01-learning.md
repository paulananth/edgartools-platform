# Search candidate completeness learning

- [x] Derive the lesson from a reproduced normal-caller mismatch — PostgreSQL passed 11 edge cases; MySQL failed the short-word method case because its default word index omits short/stop words; 2026-10-23 07:25 ET.
- [x] Add source-neutral guidance in mdm-engineering, Search candidate completeness — cover retrieval, indexed probes, version-scoped complements and recoverable derived-index upgrades; reviewed against writing-for-agents; 2026-10-23 07:25 ET.
- [x] Verify affected skill checks and review Standards, Spec and GoF — 79 role-skill/genericity cases passed in 0.96 seconds; no source names added, requested lesson only, no code design change; 2026-10-23 07:27 ET.
- [x] Publish a separate skill PR with CI evidence — PR #1146; all nine CI checks passed on afd199ff; final record-only head is checked separately before readiness; 2026-10-23 07:35 ET.
- [x] Record the late driver-loop lesson and verify the skill checks again — Writes and transactions now requires actual statement-count proof; 79 role-skill/genericity cases passed in 1.06 seconds; 2026-10-23 08:10 ET.
- [x] Learning → skill: mdm-engineering, Search candidate completeness and Writes and transactions; guidance added and genericity checks passed; 2026-10-23 07:27 ET.

The late guidance addition follows a reproduced driver-loop implementation: the replacement proves one indexed write per batch and no unchanged writes. Final-head CI is checked on PR #1146 before readiness is reported.
