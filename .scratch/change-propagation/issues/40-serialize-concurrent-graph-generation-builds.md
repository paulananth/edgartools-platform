# 40 — Serialize concurrent graph generation builds

**What to build:** Prevent two graph generation-build pipeline executions
from running concurrently, closing this map's own charted current-state
fact: "normal graph workflow tails can sync a new generation while
verifying the previously active one."

**Blocked by:** 08 — Decide graph partition reuse and candidate-generation
publication (this map)

**Status:** ready-for-agent

- [ ] A partial unique index on `mdm_graph_generation` rejects a second
  row with `status IN ('building', 'verified')` (non-terminal — not yet
  `activated` or `failed`) while one already exists, mirroring
  `uq_source_fetch_work_active_key`'s existing shape for the analogous
  concurrent-fetch problem.
- [ ] A generation build rejected by that index fails outright (does not
  queue or retry internally) — confirmed via a test that a second
  concurrent attempt gets a clear, distinguishable error rather than
  silently blocking or corrupting the first attempt's state.
- [ ] A live or integration test proves two genuinely concurrent
  `mdm sync-graph` invocations (real threads/connections, not sequential
  calls) converge to exactly one non-terminal generation at a time.
- [ ] Confirm the migration adding this index is additive/safe against
  any currently in-flight generation in prod (check `mdm_graph_generation`
  row count and status distribution before applying).

## Notes

Surfaced while resolving [08 — Decide graph partition reuse and
candidate-generation publication](08-decide-graph-partition-reuse.md) —
see that ticket's Answer. Confirmed via code search that no
mutual-exclusion mechanism (lease, lock, or unique index) currently exists
anywhere for concurrent generation builds, despite the rest of the
generation/partition schema (`MdmGraphGeneration`/`MdmGraphPartition`,
content-addressed reuse, required `--generation-id` on every CLI command)
already being fully built and correctly generation-scoped.
