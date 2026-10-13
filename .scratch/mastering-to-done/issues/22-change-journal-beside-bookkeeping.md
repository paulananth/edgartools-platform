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


- [ ] Map today's change handling per step: what each step uses now to skip
  unchanged input (receipts, content hashes, migration 017's "unchanged batches
  queue nothing", the Person and Company document selection), and where the
  Change Journal's events are written and read today (`skills/change-journal`,
  `docs/architecture/runtime-responsibilities.md`)
- [ ] Decide with the operator: what the journal records per file and step
  (the file's identity, the rules or reading version that processed it) so
  "identical or process it" is one question for every step; and how a rules or
  reading change marks every file of that source to process. No field-level or
  record-level tracking (operator: "it doesn't decide at field level")
- [ ] Redraw the README flow with Bookkeeping and the Change Journal side by
  side over all steps; widen the `CONTEXT.md` term (Change Journal, with the
  MDM Change Journal as its mastering part)
- [ ] Build it: steps ask the journal for what changed, and a reading or rules
  version change replays the whole source; tests per step
- [ ] `mdm.publish` as change data capture: map what it publishes today and
  what migration 017 already skips; publish only records and relationships
  whose published values changed (insert, update, retire), with a test that a
  second publish of unchanged records sends nothing
- [ ] Force publish: an explicit operator flag that publishes every record and
  relationship, recorded as forced; test that it sends all records after a run
  that sent none
- [ ] Relates to: the Company manifest writer's changed-document selection
  (Issue 20 / Codex readiness note), which should read this, not keep its own
