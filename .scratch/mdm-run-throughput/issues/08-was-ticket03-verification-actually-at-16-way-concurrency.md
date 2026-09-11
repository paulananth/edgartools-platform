Type: research
Status: resolved

## Question

The map's "Not yet specified" fog note asked: was Ticket 03's (batch
skip-if-unchanged source-ref lookup) 2026-09-07 wall-clock verification
(company resolution: 37.7min → 77s for a comparable-scale run) actually
captured with Ticket 02's 16-worker concurrency default already live, or
was it measured at some other (lower) concurrency level -- meaning the
map's own "real measurements, not estimates" standing preference might
still be unsatisfied for the specific "at 16-way concurrency" claim in
Decision 3's gist?

## Context

Decision 3's gist on the map states the 77s/50,735-row measurement
"decisively clos[es] this map's own 'real measurements' ask," and Ticket
04's spawning note cites the same number from the same verification run
(`mdm-mastering-batchfix-verify-1788823225`, 2026-09-07). But Ticket 03's
own `## Answer` section, written when the batching fix itself was
implemented, explicitly says the wall-clock number was **not** measured
as part of that ticket's own resolution and flags it as a "Follow-up
needed" -- so the 77s figure must have come from a *later* verification
pass than Ticket 03's own implementation session, and nothing on the map
had confirmed what concurrency setting was live for that later pass.

## Answer

**Confirmed via `git log`, not inferred:** commit `e244a571` ("fix(mdm):
parallelize run_securities/run_persons, raise resolve concurrency to 16
(#381)") merged **2026-08-09** -- a full month before the
`mdm-mastering-batchfix-verify-1788823225` verification run
(**2026-09-07**) that captured the 77s/50,735-row company measurement
Decision 3 and Ticket 04 both cite. Ticket 03's own `## Context` section
independently corroborates this: it refers to "decisions 1/2 on this map"
as already-resolved, past-tense facts at the time Ticket 03 itself was
being investigated -- consistent with decision 2 having shipped well
before decision 3.

So the 77s/50,735-row figure already reflects the cumulative effect of
Ticket 02's 16-way concurrency *and* Ticket 03's batching running
together, not batching alone at some lower/unknown concurrency. The fog
note's literal ask -- "capture that on the next prod deploy that includes
the fix... a live wall-clock before/after comparison at 16-way
concurrency in prod" -- was already satisfied on 2026-09-07. The fog note
was simply never cleared after Ticket 04 recorded the same number for its
own, different purpose (diagnosing the single-end-of-group-commit bug).

**No new live prod run was needed or run to close this ticket** -- this
is a documentation/verification gap (the map's fog section drifting stale
after the answer landed elsewhere on the map), not an unanswered
measurement question. Clearing the fog note; no new decision beyond
confirming and dating the existing one.
