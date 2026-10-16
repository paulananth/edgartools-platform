# The identifier index keeps no pending list

Priority: 96, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (MDM store migration). Status: done, merged (#1007, 2026-10-16 09:12 ET). Found by: the N-PORT Security Proving Run (ticket 79, part 1), 2026-10-15 21:26 ET.

## Why

The Merge Stage finds the Securities holding a record's CUSIP or ISIN through `mdm.stage_record_identifiers` (a GIN index, migration 007), one value at a time (binding.py, ticket 77). That index keeps PostgreSQL's default pending list (`fastupdate`): new entries wait unsorted until a vacuum merges them, and every probe reads them all. Migration 012 turned the list off for the two other indexes probed one key at a time, for this reason, but not for this one, which binding started probing later.

Measured on the Proving Run's disposable database (about 330,000 Stage records): 10,000 entries pending; one CUSIP probe took 2.5 ms (1,000 probes, 2.5 s per batch and namespace). Migration 012 measured 3 microseconds a probe with the list off. The run slowed from about 80 to 30 records a second as the store grew; this is one measured part of that, not all of it.

## What changes

- A migration: `ALTER INDEX mdm.stage_record_identifiers SET (fastupdate = off)`, then merge the entries already waiting (as migration 012 does).
- Nothing else; no source or kind named.
- Found in review: `stage_record_cross_references` (migration 005) is probed one value at a time too (`mdm.cross_reference_lookup`), so 021 turns its list off as well, by the same rule.

## Checklist

- [x] The operator's word to code it: "Goal set: fix all issues and wayfinder tickets" (2026-10-16) 2026-10-16 08:28 ET
- [x] GoF consult before code: leave it (the migration list is append-only by design; 012's populated-store test is the model); noted: the index's comment still named only `context`, so 021 rewrites it 2026-10-16 08:28 ET
- [x] The migration; a test that the index has `fastupdate=off`; the MDM migration tests pass: `021_identifier_index_no_pending_list.sql`; `test_migration_021_on_a_populated_store_turns_off_the_identifier_index_pending_list`; lookup-index tests 4 pass, the tests that read the migrations 42 pass (local PostgreSQL 16, pgserver) 2026-10-16 08:28 ET
- [x] Measured, as a whole batch rather than one probe (`research/96_measure_merge.py`, `96-measure-pending-on.json`, `96-measure-pending-off.json`): 13F's 20,311 Securities, then 40 N-PORT batches of 1,000 (store 20,311 to 60,311), once with the pending list on and once off. Mean batch 4.36 s on, 2.51 s off; the last five 3.5-5.1 s on and rising, 2.5-3.6 s off; the identifier probes of the four profiled batches 0.8-3.8 s on, 0.05-0.24 s off. How many entries waited was not measured in these runs (no `pgstattuple` in the local server); the Proving Run's 10,000 is the only count. A store of the Proving Run's size (330,000) was not rebuilt (2 h); the trend is the measure 2026-10-16 08:28 ET
- [x] The rest of the slowdown: with the list off, `mdm.save_batch` takes 1.3-1.5 s of a 2.4-2.7 s batch (no trend over the four profiled batches), matching (`propose`) 0.16-0.25 s, the closure reads about 0.23 s. Whether it stays flat at millions of records is not measured: the first thing ticket 79's HOLDS part checks 2026-10-16 08:28 ET
- [x] Three-axis review 2026-10-16 08:30 ET. GoF: leave it (the list is append-only by design; two copies of the populated-store test are not yet worth a helper). Standards and Spec (fixed): the test populated the store with the list already off, so nothing ever waited: it now puts the list back first, populates, then migrates, and asserts nothing waits where `pgstattuple` exists; the migration's comment gives both measurements; the cross-reference index added; four checklist figures corrected (the store's end, the probe range, save_batch's numbers, the pending count not measured)
- [x] PR #1007, CI green, merged on the operator's words "merge one by one" 2026-10-16 09:12 ET; main's CI green after it
- [x] Learning → skill: mdm-engineering already said to keep `fastupdate = off` on a GIN index probed one key at a time; the miss was a new caller probing an existing index. Added: when code starts probing an existing GIN index one key at a time, check that index's `fastupdate` 2026-10-16 08:30 ET
