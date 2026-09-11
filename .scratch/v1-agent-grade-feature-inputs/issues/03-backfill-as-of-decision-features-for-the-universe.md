# 03 — Backfill As-Of Decision Features for the Decision Subject Universe

**What to build:** Gold facts, derived, and factors leave the 21-CIK Ticket
42 sample and cover the Decision Subject Universe (warehouse-active ∩
MDM-active issuers, or an operator-named operating subset). Companyfacts
remain unbounded (not a 5-year fetch gate). Daily incremental wiring is
out of this ticket.

**Blocked by:** [02 — Prove one entity-facts window publishes](02-prove-one-entity-facts-window-publishes.md)

**Status:** ready-for-agent

- [ ] Distinct CIKs on gold facts, derived, and factors match the declared universe (or a written, operator-approved subset), not 21.
- [ ] New CIKs have As-Of Decision Feature rows (primary annual vector present or explicitly empty), not only raw facts with no derived/factors.
- [ ] Fetch is full companyfacts history for each processed CIK, not a 5-year cutoff.
- [ ] After this ticket, daily refresh is handed to [Bring Missing Fundamentals Artifacts Into daily_incremental](../../fundamentals-daily-integration/map.md), not started here.
