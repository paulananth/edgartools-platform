# The relationship engine follows the operator's design (GLEIF accounting parent, code)

Type: task (code)
Status: done (merged as #771)
Parent: `06-relationship-rules.md` (branch `claude/relationship-rules-inventory`)

## Operator rulings (2026-10-01)

- "Yes": start with the GLEIF accounting parent for Companies, from the files
  already local.
- Design 1, "Yes": a parent link is identified by child Company, parent
  Company and kind of parent. Dates and status are history on that link. A
  new parent closes the old link and opens a new one.
- Design 2, "Yes": a link ends only on GLEIF's own statement (inactive, or a
  stated end date). Absence from a later file never closes it.
- "Yes": write the engine code for 06a, as its own reviewed PR before the
  configuration.

## What changes

- **A link's start can be another record.** A relationship spec may name
  `source_key` and `source_source`, as it names `target_key`/`target_source`.
  A GLEIF relationship record then starts at the child's Level 1 record, so
  the link joins the child Company without the link record becoming a
  Company member. When absent, the record itself is the start, as before.
- **Identity:** `relationship_id` is the digest of type, start entity, end
  entity and scope. A restated link (new status or dates) keeps its id.
- **Periods:** each statement of one link is a period, kept apart (never
  merged into one span), with its dates, status and properties. Checks for
  overlapping parents, cycles and the calculated ultimate parent run per
  period.
- **Last seen:** each link carries the newest effective date of its
  evidence. Absence never closes a link; "not seen recently" is left to
  readers comparing `last_seen` with the latest publication.
- **Closure:** the Merge Stage gathers `source_subject` with
  `target_subject` (Python, SQL, preview scope), and
  `match_proposal_snapshot` reads it too: migration `002`.

Not here (configuration, a separate PR): GLEIF's mapping gaining
`source_key`, `gleif.relationships.v1` on Company's sources, and the parent
rules declared and proven.

## Checklist

- [x] GoF consult: leave the structure; extract the "subjects a reading's
  links name" rule into one helper (`linked_subjects`) (2026-10-01 19:30 ET)
- [x] `adapters.py`: optional `source_key`/`source_source` → `source_subject`.
  `tests/mdm/test_clean_link_start.py`, 2 passed: it starts there; without
  it the reading is byte-identical to before (assertion id pinned from the
  old adapter) (2026-10-01 19:55 ET)
- [x] `relationships.py`:
  - start from `source_subject`;
  - identity is (type, start, end, scope);
  - periods are kept apart and checked one by one;
  - `last_seen` is always present;
  - repeated reviews are dropped;
  - a period never carries identity keys.
  (2026-10-01 19:55 ET)
- [x] `merge.py`: `linked_subjects` in the closure (Python and SQL) and the
  preview scope; `link_only` readings need no binding (2026-10-01 19:40 ET)
- [x] Migration `002_link_start.sql`: `match_proposal_snapshot` reads
  `source_subject`. A store with rows at 001 takes 002 and keeps them (test);
  the snapshot changes when a link starting at its key arrives (test, fails
  without 002) (2026-10-01 19:55 ET)
- [x] `tests/integration/test_clean_relationship_identity.py`, 5 passed:
  - a restatement keeps the id;
  - a later delivery without the link leaves it open;
  - parent A, then B, then A again raises no conflict;
  - a link record starts at its child and needs no binding;
  - the snapshot.
  The first four fail on the old engine (2026-10-01 19:55 ET)
- [x] Named files pass, each under 5 minutes (2026-10-01 19:57 ET):
  - `test_clean_mdm_postgres` 46, `test_clean_identifier_binding` 24,
    `test_change_journal_source_evidence_postgres` 30;
  - `test_clean_company_one_place` 6, `test_clean_stage_binding` 7,
    `test_mdm_schema_comments` 5;
  - unit 394, MDM 486, architecture 249.
- [x] Three-axis `/code-review` (2026-10-01 19:50 ET):
  - GoF: leave it.
  - Standards: the period keys are derived from the identity; the populated
    migration test now checks behaviour; idiom fixed.
  - Spec: no blockers. Added the adapter test and the guards on `last_seen`
    and period keys.
- [x] PR #771; CI green; merged on the operator's "Yes" (2026-10-01 20:32 ET)
- [x] Tell the operator (2026-10-02, with the approvals PR):
  - GLEIF gives one period per record, so multi-period history comes with
    Forms 3/4/5 (06b);
  - "not seen recently" is the `last_seen` date, not a flag;
  - a conflict in one period sets aside the whole link (as before);
  - every link's body now has `periods` instead of top-level dates.

## For the configuration PR (06a, part 2)

- GLEIF's mapping gains `source_key: [start]`, `source_source:
  gleif.level1.v1`; `gleif_source.py:379` rewrites `target_source` and needs
  the same for `source_source`.
- `skills/data-onboarding/REFERENCE.md` (relationships row) and
  `rules/mapdoc.py` (it shows only `target_key`) learn `source_key`.
- `gleif.relationships.v1` joins Company's sources; the parent rules are
  declared, proven and approved.
