# 22: The Change Journal beside Bookkeeping, for every step

Status: open (to fix). Raised by the operator, 2026-10-13 08:17 ET.

## What the operator said

> Change journal should be at the same level as bookkeeping 1) bookkeeping
> restarts from where the load stopped 2) change journal is diff processing or
> process only the changes or changed files please make a note of it for
> fixing "mdm.publish | v Change Journal".
>
> Change journal is not just for mdm if a source parsing changes everything you
> need to process all
>
> Change journal does not micro manage it will decide a file or a source is
> identical or is needed to be processed it doesn't decide at field level
>
> MDM publish can implement cdc aka change data capture only publish what truly
> changed please make a note
>
> There has to be a force publish to publish all records

## The problem

The README's flow (`README.md`, "Mastering, from the source extract") draws the
Change Journal under `mdm.publish` only, as "durable history of delivery
intent", and `CONTEXT.md` defines only an **MDM Change Journal**. That places it
as a mastering detail. The operator's model has two peers over every step:

- **Bookkeeping**: restart. A load that stopped resumes where it stopped
  (frozen work, leases, retries, the verifier).
- **Change Journal**: what changed. Each step processes only the files that
  changed since it last ran. Its unit is a whole file or a whole source: it
  answers "identical, skip it" or "process it", never which fields or records
  inside a file changed (the step itself handles what is inside).

Two rules follow:
1. The Change Journal serves every step (capture, `source.read`,
   `source.combine`, silver, `mdm.prepare`, `mdm.merge`, `mdm.publish`), not
   MDM alone.
2. A change in how a source is read (a new reading or rules version) changes
   everything that reading produced: every file it read is processed again,
   not only files whose bytes changed.

## MDM publish: change data capture

Inside mastering, `mdm.publish` is where record-level change belongs, not in
the Change Journal: it publishes only the master records (and relationships)
that truly changed, as change data capture, never the whole master again. A
record merged again with the same values publishes nothing. Migration 017
(unchanged batches queue nothing in the outbox) is a first step; this widens it
to every published record.

A **force publish** publishes every record, changed or not: for a consumer
that is new, rebuilt or out of step. It is an explicit operator choice (a
flag on the publish command), never the default, and it is recorded as a
forced publication so a reader can tell it from change data capture. The
same holds one level up: the Change Journal's "process it" for every file of
a source (a reading or rules change) is the step-level counterpart. It
matches the repo's existing rule for SEC files: skip what is already loaded
unless an operator passes an explicit `--force` repair flag.

## Checklist


- [x] Map today's change handling per step 2026-10-13 09:10 ET (operator: "Start item 1"; branch `claude/ticket22-change-journal`):
  - **Capture** (`provider.capture`, #933): skips unchanged provider bytes with a conditional request; a 304 reuses the previous 200 capture's bytes (`workers/provider_capture.py:162-220`). File-level, but only at capture.
  - **Manifest writers** (`mdm prepare-capture`, `mdm prepare-clean-company`): name every document of the list they are given; nothing compares a document with what an earlier run processed. So a new run reads, combines and prepares every document again.
  - **Bookkeeping**: within one run, a verified unit is never redone and a resume re-checks its receipts (`engine.py` `_verify_completed`). Across runs, only resource checkpoints (`bookkeeping.checkpoint`, a revision and position per leased resource) carry over, used by ordered capture work, not by preparation.
  - **MDM**: a batch that changes nothing queues nothing (migration 017, #931): record-level, inside `mdm.merge`.
  - **Change Journal** (one append-only `journal.event` table; unique on `(producer, event_key)`; indexes on `(source, feed, id)` and `(run_id, id)`): today it receives `work.verified` (one per Bookkeeping unit, from the outbox), `capture.*` (provider capture) and `mdm.committed`. No event names the files a run processed or the rules version that processed them, and nothing reads the journal to decide what to process.
- [x] Proposed design, decided by the operator 2026-10-13 09:17 ET: "Rules + shared inputs", "Change Journal events", "--all flag, recorded" (each the recommended answer to its question):
  - **What "identical" means.** A file is identical when the Change Journal already holds, for this source, a record that this file key with this content hash (its receipt sha256) was processed under the same **processing identity**: the digest of the source's rules version together with every shared input the run reads (for Company: the Name Census and the ticker catalog). A rules or reading change, or a new census, changes the processing identity, so every file of the source is processed again (the operator's rule). Nothing finer than a file.
  - **How it is recorded.** A generic last step of a source's target, after its merge is verified, appends one `file.processed` event per file to the Change Journal. The event key spells the identity (`<source>:<processing identity>:<file key>:<sha256>`), so "was it processed?" is an exact lookup on the existing unique `(producer, event_key)` index: no new table, no table scan.
  - **How it is used.** The manifest writers look up their document list in one indexed query and name only the files without such an event; a bundle with none left starts no run. `--all` processes every file anyway (a forced run, recorded as forced).
- [x] ~~Decide with the operator: what the journal records per file and step~~ decided above, 2026-10-13 09:17 ET
- [ ] Redraw the README flow with Bookkeeping and the Change Journal side by
  side over all steps; widen the `CONTEXT.md` term (Change Journal, with the
  MDM Change Journal as its mastering part)
- [ ] Build it (branch `claude/ticket22-change-journal`):
  - [ ] GoF consult on the manifest writers (`capture_prepare.py`, `company_prepare.py`), the worker registry and the journal store
  - [ ] The processing identity: one digest of the source's rules version (its reading, Dataset Contract and policy) and every shared input's receipt (Company: Name Census, ticker catalog)
  - [ ] The journal's exact lookup of many event keys at once (a migration: one function joining the keys on the unique `(producer, event_key)` index; plan test, no sequential scan)
  - [ ] A generic last step, `journal.record`, after the merge: appends one `file.processed` event per file the run named; its verifier reads each back
  - [ ] The manifest writers name only files without such an event; a bundle with none left starts no run; `--all` names every file and the run and its events say forced
  - [ ] Each source's target gains the step (Company, Person): digests to the operator, explained
  - [ ] Proof on the installed workers: a repeat of an unchanged capture processes no file; one changed file processes only that file; a new rules version processes every file; `--all` processes every file
  - [ ] Three-axis review, PR, CI, merge on the operator's word
- [ ] `mdm.publish` as change data capture: map what it publishes today and
  what migration 017 already skips; publish only records and relationships
  whose published values changed (insert, update, retire), with a test that a
  second publish of unchanged records sends nothing
- [ ] Force publish: an explicit operator flag that publishes every record and
  relationship, recorded as forced; test that it sends all records after a run
  that sent none
- [ ] Relates to: the Company manifest writer's changed-document selection
  (Issue 20 / Codex readiness note), which should read this, not keep its own
