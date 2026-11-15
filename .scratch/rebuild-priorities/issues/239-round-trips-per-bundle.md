# 239: A bundle makes about 2,750 statements; on a hosted store each costs a round trip

Type: task. Status: open. Blocked by: none. Found by ticket 233's measurement (operator, 2026-11-15: "Start ticket 233").

## Question

Why does a persons bundle take 110 s on the hosted store and 8 to 14 s on a local one, and which statements can go?

## Evidence (ticket 233, "Measured again")

A statement log of 4 local persons bundles, grouped by shape (counts only): 10,985 statements, about 2,750 a bundle, in 156
sessions. At 43 ms to the hosted store that is 118 s, the bundle's 110 s.

| Per bundle | Statements | Why |
|---|---|---|
| `journal.record_event` | 512 | the `processed` step appends one event a file, one call each (38 s hosted) |
| `SELECT 1` with its BEGIN and ROLLBACK | about 800 | `pool_pre_ping` on every checkout of Bookkeeping, Change Journal and Rules |
| New sessions | about 36 sessions, 7 setup statements each, and the TLS handshake | one connection a command |
| The merge's own statements | about 100 | already set-based |

## Corrected, and the seven wastes (operator, 2026-11-15: "Merge should take millisecond ... Use 7 waste analysis ... not acceptable")

**The first table was wrong.** "Merging into MDM about 110 to 120 s" was the span of two receipts, the merge and the Change
Journal's `processed`. Measured per step (hosted, 8 bundles): prepare 9 s, merge 62 s, `processed` 38 s. And "the 110 s come from
per-file journal calls" was wrong too: those 512 calls were about 22 s of the 38 s `processed`, one fifth of the bundle.

**The merge is milliseconds.** Profiled on the local store (every worker process under cProfile): `merge_file` is 0.6 s for 45
batches, 13 ms a batch. What surrounds it is the cost. Per persons bundle (512 documents, about 300 records), local counts by
step window; hosted seconds measured:

| Step | Hosted s | Statements | Sessions | What the time is |
|---|---|---|---|---|
| prepare | 9 | 163 | 5.5 | a process, its sessions and checks |
| merge | 62 | 751 (MDM 544, Bookkeeping 115, Journal 92) | 10 | 20 units, each a claim, a report and about 49 MDM statements, for 13 ms of merge |
| processed | 38 | 276 (+512 journal calls before the fix) | 6.5 | Bookkeeping and journal round trips; 22 s were the 512 calls |

Statements times the hosted round trip (43 ms) gives 7, 32 and 34 s; the rest is processes started (a Python process per
status check and per worker, each with its own sessions) and waiting.

| Waste | In a persons bundle | Fix |
|---|---|---|
| Transport | 16 MB of read output and 16 MB of records pieces a bundle (4.8 GB over 149 bundles), each step reading and re-hashing its input | not the time here; measure after the rest |
| Inventory | a bundle's manifest (about 33 MB) stays; the old store's were 114 GB | clear a finished run's pieces |
| Motion | about 1,800 statements and 43 sessions a bundle; 75% are claims, checks and schema verification, about 100 are the merge | one session a worker, a check once a connection |
| Waiting | a status process before and after each pass (three Python processes a step); a 15 s pause when a pass moves nothing (`driving.py` `PAUSE`) | one status read a pass; no pause for a step that finished |
| Over-processing | **20 merge units for 512 records** (median 26 records a unit), each repeating the claim, the session and the checks | pool the unit's artifacts into batches of up to 1,000 records |
| Over-production | one journal event a file (512 calls), a 0.55 MB `processed` receipt a bundle | one statement for the file set (done) |
| Defects | a ping on every checkout, three round trips (done) | |

**Why 20 units.** `mdm.prepare` without a `publication_key` makes each read artifact its own publication and its own batches
(`_documents`, the `published is None` branch); a bundle's 512 documents are read in 8 MB slices, so 20 artifacts become 20
batches, one merge unit each. All 512 records share one effective date, so pooling them is exact. The change: cut batches
from the artifacts that share one publication time (the one batch of up to 1,000 records), keeping the batch ids and
publication identities a function of the artifacts they hold so a rerun gives the same ones. Proof: two stores, one loaded
the current way and one pooled, equal records, masters and links.

## After the first three changes (operator, 2026-11-15: "I need 50% speed", "1 statement for merge", "Step 1")

Persons, same capture and local store, statement log (counts only), with the journal's one-statement file set, the engines'
no ping, and the 8 MiB batch (PR 1811): **1,152 statements a bundle, 42 sessions, about 6 s**, from about 2,750 and 12 to 18 s.
At the hosted round trip that is about 50 s of statements against 118 s.

By database: **Bookkeeping 720 (63%) in 19 sessions, Change Journal 287 (25%) in 16 sessions, MDM 130 (11%) in 5 sessions
(all of the merge), rules 15.** A merge batch is 25 statements (2 locks, 12 reads, 9 writes, BEGIN, COMMIT; the writes are
already one `INSERT` a table), and a bundle is now 2 batches: about 50 statements.

**"One statement for the merge" is not built, on this evidence.** The reads are a dependent chain (`bound`, `holders`,
`kinds`, `identifiers_of`, `decisions_about`) with writes between that later reads see, and the matching rules run in the
engine, so a literal statement needs the rules in SQL, and two calls need an in-memory overlay and a prefetch of what a
batch can reach, with a duplicate-golden-record risk for a saving of under 100 statements of 1,152 (a second a bundle
hosted). The raw cursor is psycopg2 (no pipeline mode); queueing writes and sending them in one multi-statement query before
the next read is the safe first cut (about 25 to 18 round trips a batch). Reopen it if the merge becomes a larger share, or
for the identifier-only kinds (persons, funds, companies by an identifier), where a set-based statement is a join.

**The next cuts are the 88% that is not the merge:** Bookkeeping's 720 (claims, status before and after each pass in its own
Python process, leases, reports, schema checks) and the Change Journal's 287 in 16 sessions (each session verifies the
journal's installed schema before it appends or reads).

## Checklist

- [x] The statements of one bundle counted by a committed command (`skills/data-operations/scripts/count_statements.py`: a local store with statement logging, grouped by shape) so a change shows as a count (2026-11-15 15:09 ET)
- [x] The Change Journal appends a bundle's events in one statement (`unnest` of an array through `journal.record_event`) on PostgreSQL, the same receipts; MySQL and SQL Server unchanged. Test: 60 events were 60 statements, now 1 (`test_a_file_set_is_recorded_in_one_statement_on_postgresql`) (2026-11-15 15:09 ET)
- [x] A checkout no longer pings: the three stores' engines replace a connection older than 30 s at checkout (`pool_recycle`), which finds one dropped while idle with no statement; a shared helper was refused by the journal's independence rule and is not needed. Tests: 4 pings in 5 checkouts, now 0; an aged connection is replaced and a young one reused (`tests/unit/test_engine_checkout.py`) (2026-11-15 15:09 ET)
- [x] A merge batch is up to 8 MiB, not 1 MiB (PR 1811): a bundle is 2 merge units, not 20, since a persons record carries a 16 KB submissions row; the pooling by publication time that I first planned was wrong, the bundle is already one publication and the batches were cut by size (2026-11-15 15:26 ET)
- [ ] ~~One statement for the merge~~ deferred: under 100 of 1,152 statements now; see above
- [ ] One status read a pass, no pause after a finished step, one session a worker, a schema check once a connection
- [ ] A persons bundle measured again: local, 2,750 statements a bundle before and 1,665 after (5 bundles each, same capture); hosted seconds after the persons lane restarts on this code
- [ ] Learning → skill
