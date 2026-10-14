# The Merge Stage merges record by record

Priority: 77, tier 1, in flight (raised by the operator, 2026-10-14). Map: [Rebuild priorities](../map.md).

Type: task (code), design first. Status: claimed (Claude, 2026-10-14 08:29 ET, branch `claude/merge-per-record`). Blocked by: 74 (#960, the size caps removed). Blocks: ticket 01's ownership Proving Run.

## Why

Operator, 2026-10-14: "We are merging individual records for each kind or entity find a match if not found insert why this is complicated", then "Option 1" (redesign as its own ticket).

Today each batch loads everything its records are connected to, through every decision and every link in both directions. It replays all of it from the source records and rewrites it. Under the old 10,000 cap this stayed hidden. Without the cap, the ownership network makes every batch cost the whole network: 23 batches in 60 min, and `mdm.batch` at 49 MB (ticket 74).

## The design: each batch costs only what its records touch

Per batch (at most 1,000 records), in one transaction:

1. **Match (unchanged).** Look up each record's identifier (CIK, CRD, LEI) through its index. Join the master record it names, or insert a new one. The name rules follow, as today.
2. **The affected masters.** The masters of the batch's records, and the masters a steward decision in the batch names (merge, unbind, override, quarantine). Nothing else.
3. **Recompute each affected master, alone.**
   - Its records: `mdm.stage_record` by master id (index `stage_record_entity`).
   - Its decisions: by master id and record (`decisions_naming`).
   - Replay its identity (Rust, as today) and pick its fields by source priority.
   - Write it only if its body changed.
4. **Links stated by the batch's records.**
   - Each end's master, from `mdm.stage_record` by record key.
   - The link's id is unchanged: type, source master, target master, scope, capacity.
   - It is recomputed from its own sightings: those its stored body cites, plus the new ones. Nothing else is read.
5. **Links of a master whose identity changed.** When step 3 changes a master's id (a merge), status, kind or profiles, its links are re-checked. They are read by `source_id` or `target_id` (indexed), each recomputed as in step 4.
   - Only then. A new filing of an existing owner changes none of these, so the issuer's other owners are never read.
6. **Hierarchies only.** When a parent-type link changes (GLEIF parents, successors), its chain is walked: up to the top, and down to the records whose ultimate parent it gives. Cycles, a second parent and ultimate parents are recomputed for that chain only. Plain links (owner to issuer, custodian, auditor) never walk.
7. **Reviews.** Only about the affected masters, records and links. Old ones about the same are retired when no longer produced.
8. **Save.** Write only the rows that changed. The batch row keeps the changes, not the whole scope.

## What goes away

- The closure: the "everything connected" load and its rewrite.
- The match proposal's snapshot of the whole scope. Saves already run one at a time under the lock (`pg_advisory_xact_lock(730234)`). If the proposal is recorded, then the batch saved, in that one transaction, nothing can change in between, so there is nothing to snapshot. A refused proposal is still recorded in its own transaction, as today. This is a reading of Company Q13 ("a durable pre-commit assessment for every proposed binding"): see the question below.

## Postgres

- Every read is by key through its index (`stage_record_entity`, `source_reading_subject`, `current_record_link_start` and `_link_end`, `decisions_naming`), joined over `unnest(keys)`. No `= ANY` under `OR`; checked with sequential scans off.
- The batch's reads are made in a few set-based queries, never one query per record.
- Unchanged rows are not sent. `write_batch` writes the changed rows set-based, not one row at a time in a loop.
- No cap is chosen for a local machine: the target is hosted Postgres (Snowflake Postgres or Databricks Lakebase).

## Proof

- Old against new: an ownership slice small enough for the old code, the GLEIF fixtures, and the existing MDM integration suite. Current records and Company rows are equal; every difference is named here.
- Cost: reads and writes per batch do not grow with the network. A test saves the same batch into a small and a large network and compares the rows read.
- The ownership Proving Run, both passes, with the time per batch.

## Questions for the operator

1. The design above: approve it?
2. Company Q13: does recording the proposal and saving the batch in one transaction still meet "a durable pre-commit assessment"? The proposal row is written first, and a refused one is still kept.

## Checklist

- [ ] The operator approves the design (question 1)
- [ ] The operator answers question 2
- [ ] GoF consult before code
- [ ] Characterization tests on today's Merge Stage outputs (masters, links, reviews), kept green through the change
- [ ] Steps 1–3: affected masters, recomputed alone
- [ ] Steps 4–5: links from their own sightings; re-checked on an identity change
- [ ] Step 6: the chain walk for hierarchies
- [ ] Step 7: reviews in scope
- [ ] Step 8: only changed rows, set-based `write_batch` (a migration)
- [ ] The snapshot removed or kept, per question 2
- [ ] Old against new: no unexplained difference
- [ ] Cost test: the rows read per batch do not grow with the network
- [ ] Three-axis review; the full installed proof (a Merge Stage change)
- [ ] The ownership Proving Run, time per batch
- [ ] PR, CI green, merge on the operator's word
