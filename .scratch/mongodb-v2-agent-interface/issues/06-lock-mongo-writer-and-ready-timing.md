# Lock who writes v2 Mongo and when

Type: grilling
Status: resolved
Blocked by: 03

## Question

Who writes v2 documents, and when relative to the Snowflake READY
aggregator (`mdm reconcile` then gold refresh, one READY row, pointer
move hides agent-grade)?

Options at minimum: same aggregator process after READY; a separate
publisher that reads READY views; a Python bundle dump that ignores
READY. Fail-closed hide on pointer move must have a Mongo counterpart
or an explicit “stale docs remain readable” decision.

If hide is required: rewrite in place, tombstone/delete, or versioned
docs with an active pointer collection.

## Comments

- 2026-09-11 Operator interrupted Q1: define a Mongo data contract and
  install the MongoDB plugin before locking the writer. Draft contract:
  [data-contract.md](../data-contract.md). Plugin: official `mongodb-atlas`
  (hosted Atlas MCP + OAuth). Writer A/B/C not yet accepted.
- 2026-09-11 Data contract accepted **A** as drafted.
- 2026-09-11 Q1 accepted **A**: Separate publisher after READY, reading
  Snowflake Decision Contract objects and writing Atlas to the accepted
  data contract. Not the aggregator process. Not a no-READY dump. The
  `mongodb-atlas` plugin is the agent client, not the publisher.
- 2026-09-11 Q2 accepted **A**: In-place fail-closed hide. On pointer /
  READY move, publisher sets `readiness_state=not_ready` and
  `agent_grade=false` on docs that do not match current READY. Payload
  stays. No delete. No extra pointer collection.

## Answer

A **separate publisher** runs **after** Snowflake READY. It reads
Snowflake Decision Contract objects and writes Atlas documents that
match [data-contract.md](../data-contract.md). It is not the watermark
aggregator and not a Python dump without READY. The `mongodb-atlas`
plugin is an operator/agent client to Atlas, not this publisher.

On graph-pointer / READY move, hide is **in-place fail-closed**: set
`readiness_state=not_ready` and `agent_grade=false` on projected docs
whose watermark is not the current READY. Do not delete. Do not add a
pointer collection. The v2 agent abstains unless both flags are
agent-grade.
