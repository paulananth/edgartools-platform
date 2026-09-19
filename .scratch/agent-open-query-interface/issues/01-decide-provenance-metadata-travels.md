# Decide whether provenance metadata travels with Agent Query Surface results

Type: grilling
Status: resolved
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

- 2026-09-19 Q1 first answered "yes, by default." Operator then reversed
  this explicitly ("i changed my mind no freshness needed as part of
  agent contract") before Q2/Q3 were answered. Final answer is the
  reversal, not the first pass — recorded below. Q2 (freshness-mismatch
  flagging) and Q3 (vocabulary reuse) are both moot under the final
  answer: nothing to flag or name when nothing is exposed.

## Answer

**No provenance or freshness metadata is part of the Agent Query
Surface contract.** An Agent Query Surface result is a plain live read —
no graph generation id, no gold `run_id`, no silver-completeness flag,
no point-in-time identity of any kind travels with it, by default or on
request. This is a deliberate, explicit reversal of this ticket's first
answer, not an oversight.

Consequence for [ADR 0014](../../../docs/adr/0014-agent-open-query-surface.md):
its "Require every Agent Query Surface result to carry a full Decision
Watermark" rejected-option entry is now fully closed, not left open —
provenance was considered and explicitly declined, not deferred.

This does not touch the Snowflake Decision Contract / Mongo Decision
Projection, which keep their full Decision Watermark and Agent-Grade
Read gate unchanged for whatever still reads them (ADR 0014's own
scope boundary). It also does not resolve whether whatever eventually
forms a real Trading Decision from an Agent Query Surface read needs
some other safety story — that stays open map fog, now sharper: since
this surface carries no freshness signal at all, anything treating its
output as trade-safe would need to get that assurance from somewhere
else entirely, not from a lighter version of what this ticket declined.
