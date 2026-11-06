# 199: Rebuild mastering on three operations

Priority: 199. Map: [Rebuild priorities](../map.md). Opened 2026-11-06 10:18 ET (operator: "yes open the rebuild ticket and start"). Follows ticket 197, which holds the prototype's results.

Type: task. Status: open. Blocked by: none.

## Question

How does production mastering become the three operations (extract, load a batch to a merge stage, merge finds or creates the id), keeping what production needs, and at what cost for each thing added back?

## Method

One item at a time, built, compared with the engine and timed, as in ticket 197. Seven wastes first (operator: "always remember 7 wastes"): before moving or deleting a step, name the waste it removes and how it stays gone. Merge logic stays in the shared Rust and Python; store access stays plain, behind one layer, on PostgreSQL and MySQL. Relationships are not part of mastering (operator, 2026-11-06). They run after mastering, with or after the silver write, from the list each stored record carries.

The prototype is local scratch at `~/edgar-local-tmp/company-proto/` (`merge3.py`, `store.py`). Measurements run on mains power: a sleep at 1% battery hit one load.

## Item 1: reviews and steward actions, on the prototype

The store holds 458 open and 194 retired `binding_required` reviews and no master in review. It holds 778,637 binds, 11 merges and no steward decision, so steward cases are invented decisions on real records.

| Case | PostgreSQL | MySQL |
|---|---|---|
| Open waiting reviews, either source order | 458 of 458, same record and version | 458 of 458 |
| Exclude 1 of 11 pairs | 10 merges, 1 kept apart with a review | The same |
| Override one field | 1 of 8,361 masters changes, ids kept | The same |
| Revoke the override | 8,361 of 8,361 back to the same | The same |
| Reverse every merge, then deliver again | 0 merges re-form | The same |
| The engine's own binds and merges, reversed by the prototype, against Rust replay | 22 of 22 masters | Not run |

Each record keeps the master it was first bound to, so a reversal returns it there. Closed reviews differ from the engine's because they depend on arrival order. After a merge, the engine binds the linking record to the lowest id of the pair (11 of 11), not by any business rule, so a run compared from scratch differs on which side that record ends; only 10 of 22 groups match that way, which is why the seeded test is the proof.

No steward decision means one extra indexed read a batch: Company took 24.0 to 28.6 s under load against 22.9 s before, which is within the noise.

Not covered: chained merges reversed in dependency order, quarantine, reviews from a master conflict (none in the store), and `override_source_disagreement` is counted but not stored.

## Side research: OpenMetadata as the steward tool

Operator, 2026-11-06: "can openmedatate can be a steward tool to review and merge". From its public documentation, not tried here. It has Tasks and reviewer approvals, documented for glossary terms and asset metadata, and custom properties on existing types. No master record merge was found, and a feature request says user-defined entities are unsupported. So it can show work to a steward, but the merge stays in MDM. Not built: OpenMetadata work belongs to Codex.

## Checklist

- [x] Reviews and steward actions on the prototype: waiting reviews, exclusions, overrides, revokes and reversals, on PostgreSQL and MySQL (2026-11-06 10:32 ET).
- [ ] The same in production code, with chained reversals, quarantine and master-conflict reviews.
- [ ] Withheld values: `on_conflict: first`.
- [ ] Records set aside by classification.
- [ ] Delivery to readers: the journal, export and graph consumers, and search lookups.
- [ ] Database-side safety: leases and freshness, proved equal before the old routines go.
- [ ] Rule which rules allow a merge from the rule itself, not by source; survivor by `published_at` then id.
- [ ] Bookkeeping per file, not per batch; the `processed` step; what the step around the silver writer costs.
- [ ] Person and Fund on MySQL.
- [ ] The rebuilt path on every source, compared with the engine; the old path deleted.
- [ ] Parts from ticket 197: the catalog read in every bundle; the cost of a step whatever its work; bundles that share keys; deadlocks in claims; the batch document stored and compared many times; a resumed run stepping over retained batches; why a stored bundle is loaded again.
- [ ] Learning → skill.
