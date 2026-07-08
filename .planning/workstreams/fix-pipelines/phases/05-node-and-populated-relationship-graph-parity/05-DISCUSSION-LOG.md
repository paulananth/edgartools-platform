# Phase 5: Node And Populated-Relationship Graph Parity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-08
**Phase:** 5-node-and-populated-relationship-graph-parity
**Areas discussed:** Environment scope, Verification surface, Idempotency proof depth

**Mode:** Advisor mode (USER-PROFILE.md present). Calibration tier: `minimal_decisive`
(Vendor Philosophy: opinionated, no project-level `preferences.vendor_philosophy` override).
`NON_TECHNICAL_OWNER = false` — no signals matched; direct technical framing used throughout.

---

## Environment scope

Resolved via a direct clarifying question rather than the full advisor-research table flow,
because the user's initial free-text answer used the word "prod" — a safety-critical term in
this repo (real production, AWS `077127448006` / Snowflake `EDGARTOOLS_PROD`, must never be
touched per CLAUDE.md).

| Option | Description | Selected |
|--------|-------------|----------|
| Dev only | Prove NODE-01..06/EDGE-01..04/GVER-03 against `690839588395`/`EDGARTOOLS_DEV` only | |
| Dev then EDGARTOOLS_PRODB | Prove in dev first, then replicate the fix/config to `EDGARTOOLS_PRODB` (same AWS account boundary) via existing deploy tooling — AWS, Neo4j Native App, Postgres, Snowflake gold/graph | ✓ |
| Dev then real EDGARTOOLS_PROD | Would violate the standing hard constraint | (explicitly not chosen — confirmed) |

**User's choice:** "prove and fix everything in dev, add a step to deploy to both dev and prod,
including aws and neo4j and postgress and snowflake" — clarified via follow-up question to mean
`EDGARTOOLS_PRODB`, not real prod.

**Notes:** This uses existing, already-documented deploy tooling
(`deploy-aws-application.sh`, `deploy-snowflake-stack.sh`, the `mirror-mdm-to-snowflake.sh`
pattern, Native App activation SQL) — not new deployment automation. Recorded as D-06/D-07 in
CONTEXT.md, with D-07 specifically documenting the safety confirmation.

---

## Verification surface (NODE-01..06 / EDGE-01..04)

Resolved via advisor-research: parallel `gsd-advisor-researcher` agent investigated the
codebase and returned a 2-option comparison table (calibration tier `minimal_decisive` caps at
1-2 options).

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Extend `mdm verify-graph`'s existing check list | Add named per-type assertions over the parity data (`node_parity`/`relationship_parity`) `verify()` already computes and returns; keeps the single atomic gate wired into Step Functions `mdm_verify_graph` state and `go-live.sh` preflight | ✓ |
| (c) Pytest-only, no CLI surface | Cheaper to write in isolation, but proves SQL renders correctly, not that live Snowflake parity actually holds — wrong layer for "proven MDM↔graph parity" | |
| (b) New dedicated command (e.g. `mdm verify-node-parity`) | Researched and explicitly ruled out by the research agent before presentation — fragments the one gate every caller (Step Functions, `go-live.sh`, `run-aws-mdm-e2e.sh`) already depends on | (not presented as a viable option — trimmed by research) |

**User's choice:** (a) Extend `mdm verify-graph` — Recommended option accepted without
modification.

**Notes:** Research surfaced that `_render_verify_node_counts`/`_render_verify_relationship_counts`
already return per-type breakdowns — NODE-01..06/EDGE-01..04 are named assertions over existing
data, not new queries. `GRAPH_NODE_AUDIT_FIRM` still needs adding regardless of which option won.

---

## Idempotency proof depth (GVER-03)

Resolved via advisor-research: parallel `gsd-advisor-researcher` agent investigated the test
suite and returned a 2-option comparison table.

| Option | Description | Selected |
|--------|-------------|----------|
| Automated regression test, extend existing pattern | `tests/mdm/test_pipeline_relationships.py` already proves this pattern for 11 relationship types via real-DB-session tests, and previously caught a real "plateau-fix" bug (missing `ORDER BY` causing `LIMIT`-bounded reruns to plateau) that a mock could not have caught. Extend to 6 node types + graph-sync side. | ✓ |
| One-time documented operator verification | Matches this session's already-completed live check (15,285/15,285 nodes, 1,117/1,117 edges, stable across two runs) and the project's FINDINGS.md documentation culture, but nothing re-checks it after future code changes | |

**User's choice:** Automated regression test — Recommended option accepted without
modification.

**Notes:** The research agent found the existing real-DB idempotency test file and its prior
caught-bug history — information not provided in the original research prompt, discovered via
the agent's own codebase investigation. This raised confidence in the recommendation
significantly above a generic "tests are good" argument.

---

## Claude's Discretion

- Exact SQL/test file layout for the new per-type assertions and idempotency test extensions.
- Ordering of dev-fix-then-prodb-replicate work within Phase 5's plan waves.

## Deferred Ideas

None — discussion stayed within Phase 5 scope. Todo cross-reference (`todo.match-phase 5`)
returned zero matches; no discuss:pre or discuss:post hooks were active for this run.
