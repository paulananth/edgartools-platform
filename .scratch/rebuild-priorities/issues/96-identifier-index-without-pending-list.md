# The identifier index keeps no pending list

Priority: 96, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (MDM store migration). Status: written, waiting for the operator's word to code it. Found by: the N-PORT Security Proving Run (ticket 79, part 1), 2026-10-15 21:26 ET.

## Why

The Merge Stage finds the Securities holding a record's CUSIP or ISIN through `mdm.stage_record_identifiers` (a GIN index, migration 007), one value at a time (binding.py, ticket 77). That index keeps PostgreSQL's default pending list (`fastupdate`): new entries wait unsorted until a vacuum merges them, and every probe reads them all. Migration 012 turned the list off for the two other indexes probed one key at a time, for this reason, but not for this one, which binding started probing later.

Measured on the Proving Run's disposable database (about 330,000 Stage records): 10,000 entries pending; one CUSIP probe took 2.5 ms (1,000 probes, 2.5 s per batch and namespace). Migration 012 measured 3 microseconds a probe with the list off. The run slowed from about 80 to 30 records a second as the store grew; this is one measured part of that, not all of it.

## What changes

- A migration: `ALTER INDEX mdm.stage_record_identifiers SET (fastupdate = off)`, then merge the entries already waiting (as migration 012 does).
- Nothing else; no source or kind named.

## Checklist

- [ ] The operator's word to code it
- [ ] GoF consult before code
- [ ] The migration; a test that the index has `fastupdate=off`; the MDM migration tests pass
- [ ] Measured: one probe on a store of the Proving Run's size, before and after
- [ ] The rest of the slowdown: where the remaining batch time goes, measured (a follow-up ticket if it is not this)
- [ ] Three-axis review; PR, CI green; merge on the operator's word
- [ ] Learning → skill: mdm-engineering, GIN indexes probed one key at a time keep no pending list
