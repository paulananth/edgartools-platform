# TODOS.md Close-Out

## Destination

Every currently-open TODOS.md item (as of 2026-07-22) has either an
implementation-ready ticket or an explicit close/defer decision, so nothing
sits in backlog limbo. A one-time close-out, not a standing backlog-grooming
process — the map is done once these specific open items are dispositioned.

## Notes

- Domain: edgartools-platform, AWS-first SEC EDGAR data platform. Consult
  `CONTEXT.md` (root) and `CLAUDE.md` before introducing new terms or
  contradicting documented conventions.
- Every session should default to `/grilling` + `/domain-modeling` for
  design-tradeoff tickets; use `/research` for fact-finding that requires
  external documentation, third-party API behavior, or live infra state —
  not code already understood in this repo.
- Reviewed TODOS.md in full (2026-07-22): of ~26 entries, all but four are
  already RESOLVED/MITIGATED with evidence. This map covers exactly those
  four (well, three tickets + one already-settled decision noted below).

## Decisions so far

- **financial_derived YoY tiebreaker (Issue 3B)** — not a wayfinder ticket;
  already decided and re-confirmed. TODOS.md's own entry records a
  2026-07-18 re-evaluation ("stays deferred, decision unchanged") against
  the Ticket 20 anti-overclaim doctrine. No new decision needed here;
  revisit only if `filed_date` becomes available in silver/gold for an
  unrelated reason.

## Not yet specified

(none identified during breadth-first frontier mapping 2026-07-22 — the
four items below are believed to cover the full open surface of TODOS.md
as reviewed)

## Out of scope

(none yet — nothing has been ruled beyond this destination)
