# 22: `silver links` is built from the records that changed, not from every record

Status: resolved
Type: task

Carried from ticket 21 (and ticket 14's finish bound): after the binding moved into the database and the landing made one round trip a batch,
`silver links` still takes 581 s (9.7 min) on the hosted store against the operator's bound of five minutes for `--finish`.

## Findings (hosted, 2026-11-23 16:15 ET; read-only, three timed runs, seconds)

- `calculate` is 376 s of the 581: 65%. `Store.rows` (every database read the links make) is 281 s: 71% of `calculate`.
  - `store.bound(ends)`: 137 s. `select subject, entity_id from mastering_record where entity_id is not null and subject in (...)`, 2,000
    values a statement, 300 to 630 ms each on the server. The statistics hold 1,586 calls for 3.1 million rows.
  - `store.master_states(entities)`: 100 s. `select entity_id, kind, status from mastering_master where entity_id in (...)`, 2,000 ids a
    statement, about 315 ms each.
  - reading `linked_records`: 70 s. `current_claims` and `project`: 62 s (Python).
- Per statement the cost is on the server (random reads of a 19 GB database with about 950 MB of shared buffers), not the network: 2,000 index probes
  cost 300 ms. The same three reads run on every finish for every record, whether or not a record changed.
- The landing of the three relationship tables is now 90 s (one round trip a batch) and the binding 52 to 105 s.

## 7 wastes

| Waste | Where it shows |
|---|---|
| Over-production | Every link is recomputed from every record on every finish; a daily load changes a few thousand records |
| Over-processing | 3.2 million `bound` and 1.2 million `master_states` rows read to recompute links that are mostly the same as the table already holds |
| Transport | Those rows cross to the client to be joined in Python, though the records and masters are in the database the links are written to |
| Waiting | The finish is the last step before Gold and the mirror |
| Inventory, Motion, Defects | None found beyond the above |

## The design question

Two ways to stop reading everything; the first is the smaller:

1. **Recompute only the links whose records changed.** The stored links are a function of the claims of each record and of the masters its ends
   are bound to. A record's number (`mastering_master.changed_file`, written once with the merge's number) says which masters changed since the last
   build; `mastering_record` rows carry the merge that wrote them. Read the changed masters and the links touching them, recompute those, and leave
   the rest. Needs a stored "built up to" number and a test that the incremental result equals the whole build on the same data (the old build is the
   oracle until this is proved, then retired).
2. **Read the two lookups as one sequential pass** (a join in the database, or a streamed scan) instead of 2,000-key probes: a scan of 4.4 million
   rows is far cheaper than 2,000-row random probes, but it still reads everything every time.

The first changes what a finish costs from "every record" to "what changed"; the second only the constant. **Decide with the operator**, with this
ticket's numbers: the first is a new kind of build (an incremental one) and is not the "same output, faster" of ticket 21.

## Outcome (2026-11-23)

The operator chose the incremental build (option 1). Measuring first showed it would not shorten a **first** finish: after a full load every
record is new, so an incremental build computes everything. It helps only a daily finish. So the constant went first, each change measured on the
hosted store (`silver links`, seconds): the two lookups stream the table once (`bound` 137 to 19, `master_states` 100 to 28), a partial index
serves the records that state links (72 to 19), landing batches carry 5,000 rows (90-121 to 67), and the binding is one join pass (100 to 23).
**`silver links` is now 238.5 s (4.0 min) against the bound of five.** The incremental build is not needed for the bound; it stays an option
for a daily load that changes few records, to be decided when a daily finish is measured.

## Parts

- [x] Streamed lookups, the partial index, 5,000-row batches and the binding join pass, each with its failing-first test and its hosted figure (PRs #2074, #2076, #2075, #2077) 2026-11-23 17:04 ET
- [x] Time the hosted finish: 238.5 s clean (above) 2026-11-23 17:04 ET
- [ ] ~~Decide between the two options~~ the incremental build is deferred: the bound is met without it; measure a daily finish before building it
- [ ] ~~Tests first: the incremental build equals the whole build~~ deferred with the build
- [ ] ~~Build the incremental build~~ deferred: see the outcome
- [x] Skills: `data-operations/HOSTED-LOADS.md` ("The finish takes at most five minutes": the phase table, stream a large lookup, an index for a rare predicate, a landing batch is a round trip) 2026-11-23 17:04 ET
- [x] Learning → skill: `data-operations/HOSTED-LOADS.md`, `mdm-engineering` ("Choose the cheapest proof": measure what a design changes before building it: the incremental build would not have helped the finish it was chosen for) 2026-11-23 17:04 ET
