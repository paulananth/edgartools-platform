# Decide disposition of AdviserResolver/FundResolver's identical resolve_one() gap

Type: task
Status: resolved
Blocked by: 01

## Question

`AdviserResolver.resolve_one()` and `FundResolver.resolve_one()` have the
exact same missing-skip-if-unchanged code shape `SecurityResolver` and
`PersonResolver` had. Should this map's fix be ported to them too, purely
for shape-consistency, even though Ticket 01 found neither method has a
live caller?

## Answer

**Ruled out of scope — not fixed.** Porting the fix to dead code would be
speculative work: nothing in production or the test suite exercises
`AdviserResolver.resolve_one()`/`FundResolver.resolve_one()`, so a fix
there changes no observed behavior and adds untested-in-practice surface
area. This directly follows the precedent this map's own destination
started from — commit `091809b0`'s explicit choice not to fix
`PersonResolver` speculatively in the same pass as `SecurityResolver`,
because "the live production evidence that motivated this investigation
was specifically about security's slow tail, not person." The same
discipline applies here with an even stronger reason: it's not just
unmotivated, it's unreachable.

The real live path for adviser/fund data (`adv_bulk.py`'s
`resolve_advisers_bulk`/`resolve_funds_bulk`) was separately confirmed
safe from this bug class — see Ticket 01's Answer and this map's Out of
scope section for the adjacent bug it does have (a different shape,
tracked as release-readiness Ticket 100).

A genuinely separate, smaller question this ticket surfaced but does not
answer: should `AdviserResolver`/`FundResolver` (and their `resolve_one()`
methods) be deleted outright as dead code, or kept as intentional
resolver-class scaffolding for a future non-bulk path? Not decided here —
flagging for whoever next touches `edgar_warehouse/mdm/resolvers/adviser.py`
or `fund.py` to weigh, not blocking this map's destination.

## Follow-up (2026-08-21, `/implement 03`): decided — deleted

Investigated before deciding: grepped `.planning/` for historical evidence
of why these classes existed. Found it —
`.planning/workstreams/neo4j-pipe/phases/06-relationship-derivation-coverage/06-01-PLAN.md`
snapshots `pipeline.py`'s imports from an earlier point in this repo's
history, and at that point `pipeline.py` *did* import and presumably call
`AdviserResolver`/`FundResolver` directly. `adv_bulk.py`'s own module
docstring explains why that stopped: "Resolving those rows one at a time
turns every source record into dozens of Snowflake Postgres network round
trips" — ADV's hundreds of thousands of historical filing rows made the
row-oriented resolvers a performance problem, so `adv_bulk.py`'s batched
rewrite replaced them as the live path. The two classes were left behind
rather than deleted at that point.

No planning doc anywhere suggests a *future* revival of the row-oriented
path — the only reason to keep them would be "someone might want this
shape again," a Speculative Generality with no evidenced need. Weighed
against that: keeping unreachable code has already cost real time once —
the whole `mdm-resolver-skip-unchanged` investigation that produced this
map had to separately verify both classes were dead before it could safely
skip fixing them (Ticket 01). A future session hitting the same code
during an unrelated grep would face the identical trap: `resolve_one()`
looks like the resolver's live entry point, its bug-shape looks identical
to `SecurityResolver`'s already-fixed one, and nothing marks it as
unreachable short of tracing every caller by hand.

**Decision: delete.** `AdviserResolver`/`FundResolver` classes and their
`resolve_one`/`_existing_candidates`/`_existing_golden`/`_upsert_golden`/
`_link_to_company` methods removed from `edgar_warehouse/mdm/resolvers/
adviser.py` and `fund.py`. `ADVISER_FIELDS`/`FUND_FIELDS` — the one part
of each module still live, imported directly by `adv_bulk.py` — kept, with
each file's docstring rewritten to explain the deletion and point at
`adv_bulk.py` as the real implementation. `resolvers/__init__.py`'s
imports/`__all__` updated to drop both names.
`edgar_warehouse/mdm/coverage.py`'s one comment referencing
`AdviserResolver._link_to_company` (a now-deleted method) reworded to
describe the join directly instead of naming dead code.

Confirmed via `grep -rn "AdviserResolver\|FundResolver"` across the whole
repo afterward: only the intentional explanatory docstrings in the two
trimmed files, plus `resolvers/__init__.py`'s comment, plus
`tests/mdm/test_dashboard_readonly.py`'s pre-existing string-token
blocklist (unaffected — it's a plain-text check that these names never
appear in `dashboard_readonly.py`'s own source, not an import). Full
`tests/mdm/` suite: 533 passed (down from the sibling branch's 538 only
because that branch's PersonResolver tests aren't on this branch — no
tests reference the deleted classes at all, confirmed zero failures).
Import sanity check confirmed `ADVISER_FIELDS`/`FUND_FIELDS`/`adv_bulk`/
`pipeline`/`coverage` all still import cleanly.
