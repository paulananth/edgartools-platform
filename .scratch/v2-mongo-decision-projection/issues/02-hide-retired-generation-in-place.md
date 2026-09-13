# 02 — Hide a retired graph generation in place

**What to build:** When READY / the active graph generation moves, the
Mongo Decision Projection publisher sets `readiness_state=not_ready` and
`agent_grade=false` on projected documents that do not match the new
watermark. Payload stays. A v2 agent that requires both flags abstains.

**Blocked by:** 01 — Publish READY issuer documents to a mocked Mongo

**Status:** ready-for-agent

- [x] Pointer / READY move fail-closes prior-generation docs in place
- [x] Documents are not deleted
- [x] New READY generation can still be written as agent-grade
- [x] Tests remain mocked (no Atlas)
