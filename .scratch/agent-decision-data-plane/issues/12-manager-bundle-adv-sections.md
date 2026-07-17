# 12 — Manager bundle sections (ADV / IS_ENTITY_OF)

**What to build:** When the subject is an adviser/manager, agent-grade sections for bulk-IAPD-backed private funds / MANAGES_FUND and IS_ENTITY_OF when resolvable; heuristic ADV never agent-grade. Issuer bundles unchanged.

**Blocked by:** 11 — Subject Bundle Read (issuer).

**Status:** ready-for-agent

- [ ] Manager subjects can receive ADV/fund neighborhood sections only from bulk-IAPD-backed data
- [ ] Heuristic ADV parse cannot mark agent-grade fund edges
- [ ] IS_ENTITY_OF included when both sides resolve; valid sparse/zero cases do not hard-fail issuers
- [ ] Separate ADV watermark/lag metadata when ADV sections are agent-grade
- [ ] Issuer Subject Bundle Read behavior from 11 remains ADV not_applicable
