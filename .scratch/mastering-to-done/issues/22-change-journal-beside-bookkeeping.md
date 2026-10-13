# 22: The Change Journal beside Bookkeeping, for every step

Status: done 2026-10-13 13:17 ET; each later target ends with `journal.record` as it is built (deferred line below). Raised by the operator, 2026-10-13 08:17 ET.

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
  - **How it is recorded.** A generic last step of a source's target, after its merge is verified, appends one `file.processed` event per file to the Change Journal. The event key spells the identity (`file.processed:<source>:<processing identity>:<sha256>:<file key>`), so "was it processed?" is an exact lookup on the existing unique `(producer, event_key)` index: no new table, no table scan.
  - **How it is used.** The manifest writers look up their document list in one indexed query and name only the files without such an event; a bundle with none left starts no run. `--all` processes every file anyway (a forced run, recorded as forced).
- [x] ~~Decide with the operator: what the journal records per file and step~~ decided above, 2026-10-13 09:17 ET
- [x] Redraw the README flow with Bookkeeping and the Change Journal side by
  side over all steps; widen the `CONTEXT.md` term (Change Journal, with the
  MDM Change Journal as its mastering part). Done (operator, 2026-10-13: "Fix all issues with Ticket 22"; branch `claude/ticket22-bound-docs`): the README draws Approved Rules, Bookkeeping (restart) and the Change Journal (what changed) side by side over every step, `journal.record` after `mdm.merge`, and `mdm.publish` to consumers and the MDM Change Journal; `CONTEXT.md` defines **Change Journal**, and **MDM Change Journal** is its mastering part; overlap guard passed 2026-10-13 12:32 ET
- [x] Build it (branch `claude/ticket22-change-journal`; every part below done or deferred, 2026-10-13 13:17 ET):
  - [x] GoF consult on the manifest writers, the worker registry and the journal store: leave the structure; the new choice of files is one module both writers call (`mdm/clean/changed_files.py`), not two copies 2026-10-13 09:43 ET
  - [x] The processing identity (`changed_files.identity`): the source's readings and Dataset Contracts, the policy digest, and each shared input by name and sha256 (Company: the Name Census and the ticker catalog; Person: none) 2026-10-13 09:43 ET
  - [x] The journal's lookup of many keys at once: migration `002_found.sql`, `journal.found(producer, keys)` (at most 10,000 keys, joined on the unique `(producer, event_key)` index, custom plans), granted to the runtime, shipped in the journal wheel; `ChangeJournal.found`. Plan test with sequential scans off: the unique index, no `Seq Scan` (`test_change_journal_postgres.py`, 13 passed) 2026-10-13 09:43 ET
  - [x] `journal.record` (`workers/journal_record.py`, profile registered): one `file.processed` event per file, dated by the run's own time so a retry appends the same events; its verifier reads every event back and refuses receipts that do not name every file (`test_journal_record_worker_postgres.py`, 2 passed on a real journal) 2026-10-13 09:43 ET
  - [x] Both manifest writers (`mdm prepare-capture`, `mdm prepare-clean-company`) name only files without an event, in the caller's order; with none left the report has no manifest (no run); `--all` names every file and the events say `forced: yes`; the report's scope says how many were listed and named. Company's publication is now its documents (key and receipt), not the list file's bytes, as Person's already was (the same documents listed another way were another publication). Tests: `tests/mdm/test_changed_files.py` (6: an unchanged repeat names none; one changed file is the only one named; forcing; other rules, policy or shared input is another identity; a Company repeat and forcing; a Company census from another capture names every file); the Company and Person target tests on PG16 (12) 2026-10-13 09:43 ET
  - [x] Each source's target gains the step (Company, Person): digests to the operator, explained. The `mastering` target of each `source.yaml` gains `processed` (`journal.record`, after `merge`); no reading, field, contract or rule changes (the contract digests pinned in `test_rules_config_digests.py` are unchanged). `sec.submissions.company/source.yaml` `bd922633…` → `a511a0f7…`; `sec.submissions.person/source.yaml` `a7683b64…` → `6deca152…` Approved by the operator, 2026-10-13 10:41 ET: "Approved already merged"
  - [x] Proof on the installed workers (Person, `proof/installed_person_proof.py`; 6.3 min with the bundle install, the proof's own timer 3.7 min after it): the 1,000 pinned filers in two bundles mastered as before (386 Person records, 447 + 167 open reviews, the killed merge recovered on attempt 2, a second merge pass changes nothing, outbox 60 → 60); then the same documents again name 0 of 500 in each bundle and start no run; `--all` names 500 of 500, and both forced runs run to the end on the installed workers and change nothing in MDM; the journal holds 1,000 `file.processed` (each file's first record) and 2 `files.forced` (`proof/report-20261013-person-changed-data.json`). One changed file, and a new rules version or shared input, are proven by the tests, not on the installed workers. The Company installed proof (about 40 min) was not rerun; its helpers now expect the new step 2026-10-13 09:54 ET
  - [x] Three-axis review, findings fixed 2026-10-13 09:54 ET
    - **GoF:** leave it; noted: `changed_files` moves beside the Change Journal (out of `mdm/clean`) when a target other than mastering records files; the two writers share about six lines, extracted when a third appears.
    - **Standards, fixed:** a forced run over recorded files conflicted after its merge (same key, another body), so `--all` could never finish: now a file's first record stands, a file another run recorded first keeps that record, and a forced run records itself once (`files.forced`); test on a real journal, and the installed proof runs both forced runs to the end. A file key the journal cannot hold (2,048 bytes) is refused before any work. Noted: the 10,000-key bound is written in three places; the plan test reads a copy of the function's query.
    - **Spec, fixed:** the processing identity is now every rules file of the source's folder (Company also its load mode), so a change to any of them (Company's own `read:`, `fields.yaml`, `name-key.yaml`, `combine.yaml`) processes every file; the design line's key spelled as the code writes it; the proof times stated. Disclosed: Company's publication key now names its documents, so its consumer and batch ids change from today's.
  - [x] The Name Census part merged: #947, CI green (six checks), operator: "Merge"; merged 2026-10-13 10:58 ET as `40dc5ea5`
  - [x] Bugs fixed after the merge (operator, 2026-10-13: "Fix bugs"), branch `claude/ticket22-review-bugs` 2026-10-13 11:16 ET; PR #948, CI green (six checks, 11:23 ET), merged on the operator's "Yes" as `3a4784cb` 2026-10-13 11:28 ET:
    - A file another run recorded first was matched on its whole evidence, the file's location included, so a forced or concurrent run that read the same file from another capture folder or bucket was refused after its merge. Now matched on the file key, content hash and identity only (test on a real journal; it failed before the fix).
    - The index check ran EXPLAIN on a copy of `journal.found`'s query; it now reads the installed function's own query from the catalog, so a change to the function fails the test.
    - The installed proofs crashed with a TypeError when every document was already processed (no manifest); they now stop with a clear message.
  - [ ] ~~Every other step and source: so far the mastering targets of Company and Person record and select files. Capture already reuses unchanged provider bytes (304). Open: `source.combine` and silver landing, `mdm.publish` (CDC, below), and every other source's targets as they are built (ADV, ownership)~~ deferred to each target as it is built: checked 2026-10-13 12:32 ET, nothing else runs as a Bookkeeping target today: `source.combine` runs only inside the `mastering` target, so a file the journal names as processed is never combined; the silver writer (#879) is a command, not a Bookkeeping step; GLEIF's `mdm` target only merges batches prepared outside Bookkeeping, and MDM already skips a batch it holds; `iapd.adv` has no target; `mdm.publish` is done below. Each new target ends with `journal.record` (`skills/change-journal/SPEC.md`)
  - [x] PR, CI, merge on the operator's word: #946. First CI run failed (10:01 ET) in the Engine job: `test_active_company_preparation_caller_runs_from_installed_bundle` runs the installed `prepare-clean-company` with no Change Journal, so the new lookup had no database (it was not run locally before the push). Fixed: the test names every document (`--all`) on both sides and expects the new `processed` step; passed locally on the installed bundle (2.7 min) 2026-10-13 10:05 ET; CI rerun pending Rerun green (six checks); merged by the operator 2026-10-13 10:34 ET as `b25fe5f0`. The Name Census part (below) was pushed after the merge, so it follows on its own branch, `claude/ticket22-census-content` 2026-10-13 10:41 ET
  - [x] Company's Name Census as a shared input: operator, 2026-10-13 10:36 ET: "Only true content change is change". The census counts by its content (its name counts, normalizers and version), not by the capture and population it names, so a new capture with the same name counts processes only the files that changed. Test: a new capture where one Company's address changed names only that Company (`test_changed_files.py`; it fails under the old rule, which named all three)
  - [x] The Company installed proof on the new step, 2026-10-13 13:17 ET (44.5 min, 12:32-13:17 ET; main at `3a4784cb` with the proof's two fixes, before #949): 14 bundles, 6,726 documents; 6,414 Companies, SEC 6,414 staged and bound, GLEIF 3,716 staged and 3,052 bound, decisions `company-cik` 6,414, `sec-gleif-name-jurisdiction` 2,861, `sec-gleif-name-postal` 191; bindings equal the checkout replay; the killed merge finished on attempt 2; the second pass changed nothing (outbox 63 → 63). Ticket 22: the same 14 document lists prepared again named 0 of 6,726 documents and started no run, and the journal holds 6,726 `file.processed` events, one per document named the first time (`proof/report-20261013-company-changed-data.json`). Found and fixed on the way: since the `processed` step, the proof's preparation slice (`MASTERING[:-1]`) included `merge`, so a bundle's preparation waited for a merge it never ran; the first run (11:52 ET) looped 37 min and was stopped (now `MASTERING[:-2]`)
- [x] `mdm.publish` as change data capture: map what it publishes today and
  what migration 017 already skips; publish only records and relationships
  whose published values changed (insert, update, retire), with a test that a
  second publish of unchanged records sends nothing. 2026-10-13 12:32 ET, branch `claude/ticket22-bound-docs`:
  - Map: every outbox row sent the batch's whole `projections` (contract 2), so a batch where one of 500 records changed sent all 500; 017 skipped only a batch that changed nothing at all.
  - Migration 018: `write_batch` keeps, per record, whether it inserted or changed it (`mdm.batch_change`, by the record's position in the batch); `mdm.queue_outbox` queues the rows. The journal keeps the whole batch (contract 2: the history of what was decided). Every other consumer gets contract 3: only the changed records, each with its `change`, and no row when the batch changed none (a decision or set-aside record alone). Rows queued before 018 keep contract 2. `outbox_delivery` builds contract 3 once and `outbox_input` sends its text, so the kept hash and the sent text agree.
  - "Retire": MDM keeps no deletes (`write_batch` never removes a current record), so a record that ends (an alias, a retired review, a relationship with an end date) is an `update` whose body says so; test with a relationship that ends.
  - Tests (`test_clean_publish_changes.py`): only inserted and changed records are sent, a second publish of the same records sends nothing (receipt `unchanged`), the journal keeps the whole batch, a delivered change publishes once, rows from before 018 still send the whole batch on a store migrated with them in it, each change read by its key. Publish, outbox, merge-worker and Company tests: 50 passed; MDM and journal integration suites 338 passed before the review fixes; `tests/mdm` and `tests/unit` 1,407 passed.
- [x] Force publish: an explicit operator flag that publishes every record and
  relationship, recorded as forced; test that it sends all records after a run
  that sent none. Operator, 2026-10-13: "Current snapshot" (every current record and relationship as MDM holds it now, in pages of up to 10,000, marked forced). 2026-10-13 12:32 ET:
  - `mdm.force_publish` writes one page as a forced batch (every record's `change` is `snapshot`, the payload's `forced` true, the batch's effects say `forced`), queues one contract 3 row for that consumer, and changes no master data. Each page reads its records by key (current records, current Companies, current aliases), one record more says whether a page follows. The same run and page give the same batch. The journal and a consumer the policy does not require are refused.
  - `edgar-warehouse mdm force-publish --consumer <name> --output <folder>` writes the pages and the publish target's input manifest (`rules run --pipeline graph-publication --target publish`); the same `--run-id` gives the same pages and manifest. A separate command, not a flag on `mdm.publish`: the forced pages are batches the existing publish step delivers through its one claim, deliver and verify path.
  - Tests: after a batch that sent nothing, the pages hold every current record, Company and relationship, all `snapshot`, all forced, master data unchanged, delivered by the same path; a page late in the snapshot reads at most a page and one row from each table; a full last page is the last; the command writes the same manifest twice.
- [x] Relates to: the Company manifest writer's changed-document selection
  (Issue 20 / Codex readiness note), which should read this, not keep its own. Done by #946 and #947: `mdm prepare-clean-company` selects documents through `changed_files.select`, the Change Journal's lookup, and keeps no selection of its own (checked 2026-10-13 12:32 ET, `company_prepare.py`)
- [x] The journal lookup's 10,000-key bound (the #946 review's note, written in three places): named once in Python, `change_journal.store.FOUND_LIMIT`, used by `ChangeJournal.found` and `changed_files`; a test calls the installed `journal.found` with that many keys and one more, so the migration's bound and the constant cannot drift (`test_change_journal_postgres.py`; 25 passed with the changed-files and journal-record tests) 2026-10-13 12:32 ET
- [x] GoF consult before the publish code: leave the structure; the payload is defined in SQL and rebuilt in Python, so contract 3 is built once (`outbox_delivery`) and sent as its text; force publish reuses a batch and its outbox row 2026-10-13 12:32 ET
- [x] PR, CI, merge on the operator's word: #949. First CI run failed (12:40 ET) in Integration tests: `test_mdm_schema_comments` needs a comment on every MDM function, and the review fix added `mdm.queue_outbox` without one (the local suite ran before that fix); comment added, 25 passed locally; CI green (six checks); merged on the operator's "Merge" as `0fcadbfc` 2026-10-13 12:48 ET
- [x] Three-axis review, findings fixed 2026-10-13 12:32 ET
  - **GoF:** `write_batch` is copied whole into each migration and the outbox tail changed three days running: the tail is now `mdm.queue_outbox`, which `force_publish` calls too.
  - **Standards, fixed:** the Company and alias branches compared `('entity', id)` as a row, which the index could not bound, so a late page read every Company before it (now a key comparison; test counts the rows a page reads); a batch from before 018 missing a row for another consumer would have read as "unchanged" (now refused, test); a full last page wrote one more empty page (now a look-ahead record, test). Noted: on a policy without the journal, a batch with only a decision says `changed: true` when saved and `false` when saved again (every policy here requires the journal); pages are separate batches, so the snapshot is not one moment, and consumers apply batches in generation order (written in the spec).
  - **Spec, fixed:** no relationship in the tests (added); the force test did not show the batch before it sent nothing (asserted). Refuted: a forced page cannot make a merge stale, since a merge reads the generation under the same lock (`merge.py` `_save_assessed`). Disclosed above: "retire" is an update, and force publish is its own command.
