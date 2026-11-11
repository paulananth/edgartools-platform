# 210: Only mastering and silver touch the database

Priority: 210. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 06:41 ET (operator: "only time anything hists the database is mastering and silver. source combine must be done locally" and "why do we need verifier at all there is nothing to verify we are extracting and mergying").

Type: task, charted with wayfinder. Status: open. Blocked by: none.

## Destination

A load reads and combines captured files locally and writes files with receipts. The database is reached only by mastering (Source Stage and merge) and silver (land and derive). Read and combine have no claim, lease, heartbeat or verifier. Those steps are proved by the content hash and the Change Journal.

## Why

On the hosted store each control call costs about 2 s (a first connection 0.9 s, the frozen run 0.6 s) and each query about 43 ms, against 0.2 ms locally. A run of 553 read units takes hours in claims and checks. A combine claim composes the receipt of every unit it reads, and took over 170 s, longer than its 120 s lease: the run failed with "Stale lease" before the work started.

## Parts

- [ ] ~~Cheapest check first: control stores on the local server, MDM and silver hosted~~ ruled out (operator: "all databasees must be on the same server"). The destination guard would have accepted a lease from another database (it checks only the proof it is handed), so this was not a technical block.
- [ ] First, smaller and for every step: a long-lived `bookkeeping serve` child (one JSON command a line, one engine, a memo of the run's immutable parts) and one `Session` per thread in `control.py`; the renewal thread gets its own. Measured today: about 2 s a command (process, first connection 0.9 s, run re-validation 0.6 s) against 0.2 s of queries. GoF review done 2026-11-11 06:45 ET: serve loop is the smallest fit; never import Bookkeeping into a worker; memoize only the rules export and worklist, never the run row. Test first: ten commands open one engine and see a changed run state.
- [ ] Then measure the combine claim in a warm process (163 s measured; one store query a step did not move it).
- [ ] Design (operator rulings: no run is planned before the local steps; "drop step 6"): seven steps. Captured files; ask the journal (new or changed?); Source Extract and Combine extracts run locally through the worker modules and write files with receipts, with no claim, lease, heartbeat, verifier or Bookkeeping record; Source Stage, where the run opens with those receipts as its inputs; mastering then silver, verified; journal records processed. Bookkeeping first sees a load at Source Stage. Open: how a run's step takes receipt files as inputs where it now requires verified earlier units (`_receipt`, `_verify_item`, the `requires` chain). GoF review done 2026-11-11 07:01 ET: no provider through `_receipt`; extract the pure slot filling of `_compose` as `compose_document(body, receipt_of)` (a unit test first), and write `workers/local.py` as a small driver over `worklist()`, the workers' `execute` (they read only `input`, `output`, `checks`) and that function. A config check that a local step requires only local steps; the runner refuses a step with a generated-step cursor until a source needs it; a proof that local outputs hash the same as the database path's.
- [ ] Rule: the bookkeeping skill names which operations are verified (destination writers: mastering merge, silver land and derive) and which are not (source read, source combine). Verified by the skill lint.
- [ ] Build it, with a test that fails before the change (a read and combine of N units issue no database call).
- [ ] Prove on `local-staging`: a small load gives the same counts as before.
- [ ] Hosted OpenFIGI answers load finishes inside the operator's 1 to 2 hour window.
- [ ] ~~Claim speed fix (one store query per step in a composed input)~~ deferred: only needed if a verified step still composes many units; decide after the design.
- [ ] Learning → skill: the bookkeeping skill line that names the unverified operations.
- DECISION (2026-11-11 07:00 ET, operator: "drop step 6"): the batched "record the units" call is dropped. Read and combine leave no trace in Bookkeeping; their receipts and content hashes are their proof. The combine-claim fix (build the envelope before the lease) is moot once combine has no claim; it is only needed if the work stays a claim in the interim.

