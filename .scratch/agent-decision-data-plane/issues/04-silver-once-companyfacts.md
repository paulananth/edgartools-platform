# 04 — Silver-once skip for companyfacts (CIK + facts_parser_version)

**What to build:** Entity-facts / companyfacts re-runs skip the companyfacts API when silver already holds facts for the CIK at the current facts_parser_version; force or version bump re-fetches. Default path does not require bronze; optional persist only under ticket 01 normal-mode rules.

**Blocked by:** 01 — Dual-mode capture contract; 02 — Skip and network metrics.

**Status:** ready-for-agent

- [ ] Re-run entity-facts for a CIK with existing silver facts at current version skips network
- [ ] Force or facts_parser_version bump re-fetches and updates silver
- [ ] Metrics distinguish companyfacts network vs skip
- [ ] Agent-grade financial readiness no longer depends on mandatory companyfacts bronze by default (aligns ADR 0002)
