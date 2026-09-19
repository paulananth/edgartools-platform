# Decide whether provenance metadata travels with Agent Query Surface results

Type: grilling
Status: claimed
Blocked by: none

## Question

The operator chose an open-query interface: no fixed bundle, no
Agent-Grade Read gate on every query (ADR 0014). That removes
*gating* — a query is never blocked because a watermark component is
missing or misaligned.

Gating and provenance are separable. Does every Agent Query Surface
result still carry inspectable provenance metadata — for example, which
graph generation a relationship edge came from, which gold `run_id` a
feature was computed under, whether silver was complete for the rows
touched — even though the platform never blocks the query because of
it?

Lock:

1. Does the agent get this metadata by default on every result, does it
   get it only on request, or is it not exposed at all (the agent reads
   current live state with no provenance story)?
2. If exposed: does the agent get an explicit signal when a query spans
   data of different freshness (for example, a gold feature computed
   under one `run_id` joined against a graph edge from a different
   generation) — flagged in the result, or left for the agent to notice
   from raw metadata fields?
3. Does this reuse Decision Watermark vocabulary (`CONTEXT.md`) for the
   metadata shape, or does the Agent Query Surface need its own,
   lighter-weight provenance vocabulary since it isn't gating a Trading
   Decision the way a Decision Watermark does?

## Comments
