# 03 — Backfill As-Of Decision Features for the Decision Subject Universe

**What to build:** Gold facts, derived, and factors leave the 21-CIK Ticket
42 sample and cover the Decision Subject Universe (warehouse-active ∩
MDM-active issuers, or an operator-named operating subset). Companyfacts
remain unbounded (not a 5-year fetch gate). Daily incremental wiring is
out of this ticket.

**Blocked by:** [02 — Prove one entity-facts window publishes](02-prove-one-entity-facts-window-publishes.md) — unblocked (resolved 2026-09-11), but read its Answer before starting: it found `bootstrap-fundamentals` never reaches Snowflake landing on its own (see note below).

**Status:** ready-for-agent

- [ ] Distinct CIKs on gold facts, derived, and factors match the declared universe (or a written, operator-approved subset), not 21.
- [ ] New CIKs have As-Of Decision Feature rows (primary annual vector present or explicitly empty), not only raw facts with no derived/factors.
- [ ] Fetch is full companyfacts history for each processed CIK, not a 5-year cutoff.
- [ ] After every window this ticket runs, `edgar-warehouse backfill-silver-landing-historical --run-id <id>` (or equivalent) also runs, so the backfilled CIKs actually reach Snowflake landing/gold — Ticket 02 found `bootstrap-fundamentals` never triggers landing export on its own (not in `SOURCE_EXPORT_COMMANDS`, and `gold-refresh` doesn't cover it either). Verify with a live before/after Snowflake landing CIK count, the same way Ticket 02 did.
- [ ] After this ticket, daily refresh is handed to [Bring Missing Fundamentals Artifacts Into daily_incremental](../../fundamentals-daily-integration/map.md), not started here.
