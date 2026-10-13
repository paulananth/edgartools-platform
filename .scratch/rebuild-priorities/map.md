# Rebuild priorities

Labels: wayfinder:map. Charted 2026-10-13 ET, from the 70 tickets left open after the stale-ticket cleanup (mastering-to-done ticket 25).

## Destination

The rebuild carries the captured data end to end, and proves it. Every captured feed has a reader and a Dataset Contract. Company, Person, the ownership links, Security and the financials are mastered, written to silver, and readable through `edgar-warehouse context`. The operator accepts both the recreation proof (ticket 32) and the financials cohort proof (ticket 48).

## Notes

- **Ticket number = priority.** Ticket 01 is the most urgent. The frontier is the lowest-numbered ticket that is open, not blocked and not claimed. The order rule (operator, 2026-10-13, "Agreed"):
  1. **Tickets 01–08, in flight:** work already started, or blocked only on the operator's answer.
  2. **Tickets 09–32, the recreation proof:** what the proof needs, in dependency order.
  3. **Tickets 33–62, product value:** the financials first, then the promotion criteria, the agent decision inputs and the dashboards.
  4. **Tickets 63–67, housekeeping:** needs no SEC requests.
  5. **Tickets 68–71, gated:** each needs SEC requests or AWS. They wait for the operator's permission.
- **Execution is in scope.** This map carries build tickets as well as decisions, like the profiling map does. Each build ticket gets:
  - its own branch, cut fresh off origin/main, in its own worktree;
  - a GoF consult before code;
  - a three-axis `/code-review` (Standards, Spec and GoF);
  - the overlap guard before every commit and push;
  - CI green;
  - a merge only on the operator's word.
- **Moved tickets keep their history.** Each ticket was moved from its own effort, and the old path holds a one-line "moved" note. The old effort's map keeps its decisions. In a Blocked by line, a list of numbers uses this map's numbers, or names the old effort ("mastering-to-done 03") when that ticket was not moved. Free text keeps the old effort's numbers.
- **Standing rules:**
  - no sec.gov request and no prod change without the operator's permission;
  - the repo is public, so fixtures are invented and outputs hold counts only;
  - every lookup uses an index;
  - names are the source's own;
  - each checklist part is ticked with its evidence and an ET time.
- **Open question for the operator (blocks ticket 01's next part):** does the ownership feed create owner records of its own, or only link to owners mastered from submissions?

## Decisions so far

- [Which measures analysts use, and the reported concepts behind each](issues/33-company-financials-01-which-measures-and-concepts.md): 19 line items by usage, concepts chosen per period, years keyed on period end
- [Capture permission and route for company facts](issues/34-company-financials-02-capture-permission.md): one bounded capture now, local only (operator, "a")
- [Capture the cohort's company facts](issues/36-company-financials-04-capture-the-cohorts-company-facts.md): 329 of 500 Companies have facts; 5.1 million facts in long form

## Not yet specified

- **Where gold stands in the rebuild.** The agent decision inputs, the unified Company dimension, the dashboards and the promotion criteria (tickets 49–62) were written against the Snowflake gold layer. Once the silver writer (ticket 17) and the context views (ticket 18) land, each needs a decision: re-point it at the rebuild's silver, or retire it.
- **Hosting the rebuild.** Hosted Snowflake Postgres (ticket 68) and the AWS worker runtime (ticket 71) need the operator's destinations. The order of hosting and the recreation proof is not yet set.

## Out of scope

- The retired pipeline: the daily, bootstrap and load-history commands, their state machines, the DuckDB silver store and the old MDM runs. 77 tickets about them were deleted on 2026-10-13 (mastering-to-done ticket 25), and git history keeps them.
