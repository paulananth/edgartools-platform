# Decide Cold-Start / Bootstrap Behavior

Type: grilling
Status: resolved
Blocked by: 02

## Question

MDM's matching engine (`match.py`) scores incoming records against
`candidates` — the existing, already-resolved entity population in MDM's
Postgres. Today that population is fully built (Stage 2 runs after all of
silver exists), so by the time any matching happens, the candidate pool is
maximally complete. Under MDM-ahead-of-silver, the very first window of a
brand-new universe load (`load_history`'s first `WindowedBootstrap`
window, or MDM's own historical first-ever run against this platform) has
**no existing MDM entities to match against at all** — every record in
that first window is definitionally a new/unresolved entity, and every
subsequent window's candidate pool is only as complete as everything
resolved so far, not the full eventual universe.

Does this change matching quality or correctness in a way that matters?
Two related sub-questions, both resolved by [Decide the Coupling Mechanism
Between MDM and Silver's Write Path](02-decide-coupling-mechanism.md)'s
answer first (a synchronous vs. two-phase coupling likely has different
cold-start failure modes — e.g. a two-phase design's backfill pass could
plausibly re-resolve early windows once the candidate pool has grown,
where a synchronous design commits its match decision permanently at
window time): should an entity resolved confidently in window 1 (e.g.
auto-merged as new) ever be re-evaluated once window 50 reveals it should
have matched something from window 3? Is a "backstop" full-universe
re-resolution pass (matching today's Stage 2 semantics) still needed
periodically even after this change, specifically to catch cross-window
matches the per-window batching structurally can't see at commit time?

## Deliverable

A decision: whether cold-start/incomplete-candidate-pool effects are
acceptable as a permanent characteristic of the new order, need a
mitigation (e.g. a periodic backstop re-resolution pass), or are severe
enough to change the coupling/batching decisions made in ticket 02.

## Answer

**Not a new risk class — no mitigation required as part of this map.**
Verified against the actual code, not assumed: today's after-silver Stage
2 pass (`run_companies`: `SELECT cik FROM sec_company`, effectively
CIK-ordered; `run_persons`: `ORDER BY o.accession_number, o.owner_index`,
`pipeline.py:337,806`) already processes rows **sequentially**, querying
candidates **live** against MDM Postgres as it goes (confirmed in ticket
01) — company #30,000 in today's single full-universe pass already only
sees entities resolved from companies #1–29,999, never later ones. Moving
resolution to per-window (ticket 03's four in-scope commands, sequential —
`WindowedBootstrap` runs at `MaxConcurrency=1` per CLAUDE.md) is the exact
same live-query, order-dependent model, just chunked into ~124 windows
instead of one pass. Nothing about "ahead of silver" specifically
introduces incomplete-candidate-pool effects that don't already exist in
today's design — the ticket's original framing (window 1 has "no existing
entities to match against") is true, but is equally true of row 1 in
today's full-universe pass; it isn't a property of the reordering.

**A periodic full-universe backstop/reconciliation pass is a legitimate,
distinct future idea — not decided or designed by this map.** Not needed
for correctness (per the above), but genuinely useful independent of this
change: any order-dependent live-query system will occasionally produce
low-confidence near-misses (two records that should match but each
scored just under threshold when their own window ran), and a periodic
pass over the full population could catch those a strictly sequential
system structurally can't. Flagged as out of scope for this map, not
because it's unimportant, but because it isn't required by the decision
this map is making — a future map or ticket, not blocked on anything
here, would own designing it.
