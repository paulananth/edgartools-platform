# Research the Rules Database schema: one table, or a flexible design

Type: research
Status: resolved (2026-09-26)
Blocked by: none

## Question

Ticket 06 decided that a **Rules Database** is the master store for every
version of every Source Contract (the source's configuration and its data
mapping) and every Mastering Policy (the merge rules). Spec §4.5 says its
schema was never designed ("Not prototyped: … the Rules Database schema").

The operator asked on 2026-09-26: "first create a new database for storing
the config and merge rules for source and data mapping; research for a one
table design or a flexible easy to maintain design".

From primary sources, compare these shapes, with DDL for each:

1. one append-only table for everything;
2. one immutable table of versions, plus one append-only table of events
   (state changes, proofs, approvals);
3. normalized tables for each kind (source, mapping, policy, rule, ...).

Measure each one against the operator's direction (2026-09-26 13:03 ET: a
lean, clean, KISS MDM, sources fully decoupled, new MDM fields easy to add,
remove a layer rather than tune it):
- what adding a new MDM field costs (the target is no migration);
- what adding a new source costs;
- what adding a new kind of rule costs;
- whether "current" is derived, never stored;
- whether any version body is kept in two places.

## Fixed by earlier decisions (not reopened here)

- Its own Postgres, separate from Clean MDM's `mdm_v2`; local first.
- Each version is stored as canonical JSON with its SHA-256 digest, and a
  stored version never changes.
- Lifecycle: draft → proven → active → retired.
- A proof is pinned to the batch hash it ran on. An approval records the
  approver, the time and the exact digest.
- The digests of custom code and fixtures are recorded with the version.
- Production never reads the Rules Database. Activation is a hand-off into
  Clean MDM through `register_dataset` and `register_policy`.

## Also answer

- A separate database, or a separate schema? Ticket 06's wording allows
  either.
- With the Rules Database as the master, can Clean MDM keep less? Today
  `mdm_v2.dataset` and `mdm_v2.dataset_mapping` both hold the contract body,
  and five readers still read the first reading from `dataset` (found
  2026-09-26 while answering "why two tables").

## Answer

**Research:** [11-rules-database-schema.md](../research/11-rules-database-schema.md)
(evidence; its schema ran on PostgreSQL 16.15). It proposed two tables, a
`version` table and an `event` table, with each version's state derived from
its events.

**Decision (operator, 2026-09-26, with the approved rules-skill plan):**
files in git plus **one** table.
- People and agents edit `rules/` files, which are reviewed in PRs. The
  database records each version and its status; it is not the master. This
  changes ticket 06's "the Rules Database is the master store".
- The table is `rules.rule_version`: one row per version.
  - The body never changes.
  - Status only moves forward: draft → proven → active → retired.
  - A partial unique index allows one active version per name.
  - Approval columns are filled only by an approver's own login.
- Migration runs both ways: any file to the database, and the database back
  to files.
- The database is separate from `mdm_v2`, as the research recommended.

The design and the build are the rules skill's work:
`.scratch/rules-skill/plan.md` ("Design at a glance") and ticket 02
("The Rules Database"). The research's §6 finding stays open as its own
question: `mdm_v2.dataset` can shrink to a list of source codes once its
five readers move.
