# v1 Agent-Grade Feature Inputs

**Status:** ready-for-agent
**Parent:** [v1 Agent-Grade Inputs](../agent-decision-v1-inputs/map.md)

Implementation tickets for As-Of Decision Features only (the factor
vector). Insider and employment identity stay on the parent wayfinder
until grilling closes. Snowflake Decision Contract objects stay on
[Agent Decision Contract](../agent-decision-contract/map.md).

Daily companyfacts refresh is **not** reticketed here. After ticket 03,
pick up [Bring Missing Fundamentals Artifacts Into
daily_incremental](../fundamentals-daily-integration/map.md) (retirement
conflict, then Step Functions wiring). Full-universe history is
`load_history` Stage 1B, not a 5-year fetch gate.

Frontier: tickets 01 and 02 (no blockers). Ticket 03 waits on 02.
