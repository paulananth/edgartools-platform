# 03 — Run the publisher after the READY aggregator

**What to build:** The warehouse READY path invokes the Mongo Decision
Projection publisher after the watermark aggregator writes READY, not
inside the aggregator. v1 Snowflake Agent View is unchanged. CI still has
no Atlas secrets.

**Blocked by:** 01 — Publish READY issuer documents to a mocked Mongo; 02 — Hide a retired graph generation in place

**Status:** ready-for-agent

- [ ] Publisher is not called from the observe-only aggregator body
- [ ] READY completion is the gate before Mongo writes
- [ ] Agent View Mode still reads Snowflake Decision Contract objects only
