# 02 — Agent View vs Explore placement for ER widgets

Type: grilling  
Status: resolved  
Blocked by: 01  

## Question

Should ER dashboards run primarily in Agent View (contract-only), Explore, or dual with skill-specific rules? Can ERDP-03/07 ever appear in Agent View?

## Answer

**Dual-mode chrome retained; ER desk workflows are Explore-first.**

| Surface | Mode |
|---------|------|
| Watermark / Feature Screen / Bundle audit strip | Agent View default OK |
| Calendar, free gold history, EOD multiples, future consensus/guidance/transcript | **Explore only** |
| Pure-SEC quality screen ranks | Agent View via Feature Screen; Explore for free factor tables |

**Hard rule:** Do not add `EARNINGS_CALENDAR`, PriceProvider outputs, or future ERDP-01/02/04 tables to `AGENT_VIEW_ALLOWED_OBJECTS` without a new ADR superseding pure-SEC Decision Features.

Labels: every non-SEC Explore widget shows `source_system` + `grade=explore`.

See [data-mode-matrix.md](../assets/data-mode-matrix.md), `docs/dashboard-agent-view-explore.md`, ADR 0001, ERDP-06.
