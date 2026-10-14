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
- **Answered (operator, 2026-10-13 20:30 ET, "Create its own (Recommended)"):** the ownership feed masters each reporting owner (Person or Company, by CIK) together with its insider link; it does not wait for the submissions feed.

- **Answered (operator, 2026-10-14 08:19 ET):** Form ADV's custodian links come back once the Merge Stage has no limit (ticket 75, "Yes, a new ticket"); the GLEIF cascade and Form ADV matching rules, declared but not switched on, are measured and then switched on or deleted (ticket 76, "Track them on the map"). For the ownership feed, a ten-percent owner is linked `BENEFICIAL_OWNER_OF` ("BENEFICIAL_OWNER_OF (Recommended)"), and a random 50 of the 198 owners with no submissions document are checked before its switch-on ("Check a sample first (Recommended)"); both are recorded in ticket 01.

## Decisions so far

- [Which measures analysts use, and the reported concepts behind each](issues/33-company-financials-01-which-measures-and-concepts.md): 19 line items by usage, concepts chosen per period, years keyed on period end
- [Capture permission and route for company facts](issues/34-company-financials-02-capture-permission.md): one bounded capture now, local only (operator, "a")
- [Capture the cohort's company facts](issues/36-company-financials-04-capture-the-cohorts-company-facts.md): 329 of 500 Companies have facts; 5.1 million facts in long form
- [MDM is just MDM: the words](../mastering-to-done/issues/26-mdm-is-just-mdm.md): "Clean MDM" is "MDM" in every living word (#956); the code names are ticket 73
- [Switch on Company and the GLEIF parents](issues/02-mastering-to-done-06-switch-on-company-and-gleif-parents.md): merge version approved and active locally; source activation moved to Bookkeeping on AWS
- [Bookkeeping without legacy or custom code](issues/03-mastering-to-done-20-bookkeeping-without-legacy-or-custom-code.md): every step a worker and verifier; the capture worker is #933; the live SEC run waits for AWS
- [Rust engine core behind Python](issues/04-mastering-to-done-15-rust-engine-core-behind-python.md): #799; streaming and multi-input steps are tickets 16 and 17
- [Self-sustaining data skill](issues/05-mastering-to-done-21-self-sustaining-data-skill.md): Company, GLEIF and Person read on the engine, old readers deleted, G3 passed again
- [Relationship rules](issues/06-platform-validation-06-relationship-rules.md): GLEIF parents and insider links switched on; Person feed 1 is ticket 11
- [Match proposal snapshot scaling](issues/07-platform-validation-05b-match-proposal-snapshot-scaling.md): the snapshot is gone; batch times flat over the full Person feed
- [Proving Run on a pinned cohort](issues/08-company-mastering-05-run-a-proving-run-on-a-pinned-cohort.md): whole population proved (6,414 Companies, 3,052 GLEIF bindings)
- [Check a step without redoing it](issues/72-check-a-step-without-redoing-it.md): a check confirms inputs, contract and output shape, and redoes the first unit and a 5% sample (#958)
- [The Merge Stage has no limit](issues/74-merge-stage-has-no-limit.md): no size refusal anywhere; how the input is cut stays (#960)
- [The Merge Stage merges record by record](issues/77-merge-one-record-at-a-time.md): a batch reads only the masters it touches and their links; proposal and batch in one transaction; the outbox reads a batch once (#963)

## Not yet specified

- **Where gold stands in the rebuild.** The agent decision inputs, the unified Company dimension, the dashboards and the promotion criteria (tickets 49–62) were written against the Snowflake gold layer. Once the silver writer (ticket 17) and the context views (ticket 18) land, each needs a decision: re-point it at the rebuild's silver, or retire it.
- **Hosting the rebuild.** Hosted Snowflake Postgres (ticket 68) and the AWS worker runtime (ticket 71) need the operator's destinations. The order of hosting and the recreation proof is not yet set.

## Out of scope

- The retired pipeline: the daily, bootstrap and load-history commands, their state machines, the DuckDB silver store and the old MDM runs. 77 tickets about them were deleted on 2026-10-13 (mastering-to-done ticket 25), and git history keeps them.
