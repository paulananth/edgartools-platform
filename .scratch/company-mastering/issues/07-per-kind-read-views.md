# Present the one evidence table as a shelf per kind

Type: task
Status: done — migration 033, 2026-09-23

## Question

Does Clean MDM need a Company stage and a Person stage, or one table for every
kind? Asked by the operator on 2026-09-23, after settling that the Merge Stage
updates the master record rather than duplicating it.

## What exists

One table per role, with the kind as a value inside it, and this is true of both
the old design and the new one:

- `mdm_v2.assertion` holds every source statement about anything
  (`023_clean_mdm.sql:39-49`); the kind is in the hashed body.
- `mdm_v2.identity` holds one row per entity with `kind` as a column, permitting
  eight values (`023_clean_mdm.sql:50-56`).
- `mdm_v2.projection` holds the master record for every kind
  (`023_clean_mdm.sql:64-70`).
- The legacy `mdm_entity_attribute_stage` was likewise one table for all kinds,
  keyed `(entity_id, source_system, source_id, field_name)`
  (`001_initial_schema.sql:180-191`).

The kinds are already separated where it decides outcomes: the Mastering Policy
holds its own field rules, priorities, version and digest per kind
(`kinds.company`, ticket 02 decision 3).

## Decision (operator, 2026-09-23)

**Keep one table and add a read view per kind.** Three reasons, in order:

1. One filing touches two kinds at once — a Form 4 is an issuer and a reporting
   owner in one read, one transaction, one batch (ticket 03 decision 2). Split
   tables make every ordinary piece of work span two tables.
2. The shapes are identical. Every statement is source, record, revision, claim
   and provenance; the claim is jsonb, so no kind wants a column another does
   not have.
3. A ninth kind costs one word rather than a table, its triggers, its
   migrations, and every query taught about it.

Rejected: per-kind tables, for the above. Rejected: materialised per-kind
copies, which add a refresh, a lag and a backfill to buy nothing a view lacks.

## What maintenance actually costs

This was the operator's follow-up question, and it splits in two:

- **A new field costs nothing.** Fields are keys inside `body->'fields'`, so a
  field the policy has never carried arrives as a new row in the exploded view
  and a new key in the whole-record view. No migration, no view edit. Proved by
  `test_a_field_no_view_names_needs_no_migration`.
- **A new kind costs four views**, which is one word in migration 033's array,
  because the views are generated in a loop rather than written out.

Two things can silently rot, and both are now held closed rather than trusted:

- **The kind list.** It cannot be derived across the SQL/Python boundary. The
  migration refuses to install if its own array differs from the CHECK
  constraint on `mdm_v2.identity`, and
  `test_one_view_per_kind_per_shape_and_no_others` holds `evidence.KINDS` equal
  to that same constraint. `classification.CLASSIFICATION_VERDICTS` was a third
  hand-written copy, added in #698; it is now derived from `KINDS`.
- **The column list.** A view freezes its columns at creation, so `SELECT *`
  would keep showing the old set after a structural column was added to the base
  table. The views list columns, and
  `test_a_whole_record_view_shows_every_column_of_its_base_table` fails until a
  new base column is added to 033.

## Built

`033_clean_mdm_per_kind_views.sql` — four views per kind, generated from one
guarded array:

| View | One row per |
|---|---|
| `<kind>_evidence` | source record, whole claim |
| `<kind>_evidence_field` | (source record, field) — the stage shape |
| `<kind>_master` | entity |
| `<kind>_master_field` | (entity, field), naming the source that won and counting the losers |

Plus the two expression indexes the views need — `assertion((body->>'kind'))`
and a partial one on entity projections — without which every per-kind view is a
sequential scan. 025 indexed the subject; nothing read the kind until now.

**One hazard found and closed.** A single-table view with no set-returning
function is auto-updatable in PostgreSQL, and `information_schema` confirms
`company_evidence` is insertable and updatable. An INSERT through it would reach
`mdm_v2.assertion` and bypass `commit_batch` entirely — the `immutable_row`
trigger does not help, because it fires on UPDATE and DELETE, not INSERT. What
refuses the write is the privilege: `store.migrate()` revokes and re-grants
`SELECT` across the whole schema after every migration, and `ALL TABLES` covers
views. That is proved rather than assumed
(`test_the_privilege_is_what_refuses_the_write_not_the_view_shape`), because the
refusal test would otherwise pass for the wrong reason if the shape ever changed.

## Not done

- **Migrations 027-033 are not applied to the live store.** Codex checked
  read-only and found 023, 025 and 026 recorded. `mdm migrate` does not run on
  deploy; merged and applied stay separate facts.
- The kind list could be collapsed to one authority by making it a seeded table
  with `identity.kind` as a foreign key. Not done: it rewrites a constraint on a
  live table to save a guard that costs six lines and fails loudly. Worth
  revisiting when a ninth kind actually arrives.
