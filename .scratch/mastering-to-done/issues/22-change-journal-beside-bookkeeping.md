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

## The problem

The README's flow (`README.md`, "Mastering, from the source extract") draws the
Change Journal under `mdm.publish` only, as "durable history of delivery
intent", and `CONTEXT.md` defines only an **MDM Change Journal**. That places it
as a mastering detail. The operator's model has two peers over every step:

- **Bookkeeping**: restart. A load that stopped resumes where it stopped
  (frozen work, leases, retries, the verifier).
- **Change Journal**: what changed. Each step processes only what changed since
  it last ran: changed files, changed records, changed outputs.

Two rules follow:
1. The Change Journal serves every step (capture, `source.read`,
   `source.combine`, silver, `mdm.prepare`, `mdm.merge`, `mdm.publish`), not
   MDM alone.
2. A change in how a source is read (a new reading or rules version) changes
   everything that reading produced: every file it read is processed again,
   not only files whose bytes changed.

## Checklist

- [ ] Map today's change handling per step: what each step uses now to skip
  unchanged input (receipts, content hashes, migration 017's "unchanged batches
  queue nothing", the Person and Company document selection), and where the
  Change Journal's events are written and read today (`skills/change-journal`,
  `docs/architecture/runtime-responsibilities.md`)
- [ ] Decide with the operator: what the journal records per step (input
  identity, the rules or reading version, output identity) so "changed" is one
  question for every step; and how a rules or reading change marks everything it
  read as changed
- [ ] Redraw the README flow with Bookkeeping and the Change Journal side by
  side over all steps; widen the `CONTEXT.md` term (Change Journal, with the
  MDM Change Journal as its mastering part)
- [ ] Build it: steps ask the journal for what changed, and a reading or rules
  version change replays the whole source; tests per step
- [ ] Relates to: the Company manifest writer's changed-document selection
  (Issue 20 / Codex readiness note), which should read this, not keep its own
