# 199: Rebuild mastering on three operations

Priority: 199. Map: [Rebuild priorities](../map.md). Opened 2026-11-06 10:18 ET (operator: "yes open the rebuild ticket and start"). Follows ticket 197, which holds the prototype's results.

Type: task. Status: open. Blocked by: none.

## Question

How does production mastering become the three operations (extract, load a batch to a merge stage, merge finds or creates the id), keeping what production needs, and at what cost for each thing added back?

## Method

One item at a time, built, compared with the engine and timed, as in ticket 197. Seven wastes first (operator: "always remember 7 wastes"): before moving or deleting a step, name the waste it removes and how it stays gone. Merge logic stays in the shared Rust and Python; store access stays plain, behind one layer, on PostgreSQL and MySQL. Relationships are not part of mastering (operator, 2026-11-06). They run after mastering, with or after the silver write, from the list each stored record carries.

The prototype is local scratch at `~/edgar-local-tmp/company-proto/` (`merge3.py`, `store.py`). Measurements run on mains power: a sleep at 1% battery hit one load.

## Checklist

- [ ] Reviews and steward actions: review records, overrides, merge exclusions, reversals.
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
