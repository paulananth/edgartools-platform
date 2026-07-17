# 09 — Decision Watermark and Agent-Grade gate

**What to build:** Snowflake Decision Contract core: Decision Contract Version, composite Decision Watermark (published completeness claims, gold run_id / feature as-of, graph generation, high-severity reconcile disposition), and fail-closed Agent-Grade Read when components missing or misaligned. Bronze content hashes only when persist was used.

**Blocked by:** 08 — Snowflake export expansion for issuer neighborhood evidence.

**Status:** resolved

- [x] Contract exposes Decision Contract Version on agent-facing results
- [x] Decision Watermark identity is queryable and bound into agent-grade results
- [x] Misaligned or incomplete watermark components yield non-agent-grade (fail closed), not best-effort joins
- [x] Graph parity / verify-graph (or equivalent published flag) is required for agent-grade
- [x] Open high-severity reconcile findings block agent-grade unless explicitly waived in watermark metadata

