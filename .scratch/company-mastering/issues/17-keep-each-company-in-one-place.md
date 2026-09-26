# Keep each Company in one place

Type: task
Status: claimed (Claude, branch `claude/company-mastering-17-company-one-place`, 2026-09-26 13:10 ET)
Blocked by: none
Blocks: Phase 2 of the Proving Run (ticket 05) at whole-population scale

## Outcome

The Merge Stage writes each Company to the dated Company table
(`mdm_v2.company`, with `mdm_v2.company_alias` for a merged-away ID) and
reads it from there. `mdm_v2.projection` holds no Company. The copy steps
between the two go, and consumers receive the same objects as today.

The operator chose this on 2026-09-26 at 13:03 ET, over tuning the slow copy
step: "do not add extra work, we need a lean and clean and KISS-based simple
MDM with fully decoupled source and easy to add new MDM fields".

## Why

Today one Company is written three times in one commit, then rebuilt a
fourth time at delivery:

1. The Merge Stage (Python) computes the Company and sends it in the batch.
2. `commit_batch_core` writes it to `mdm_v2.projection`.
3. The trigger `project_company_version` copies it to `mdm_v2.company`
   (`record_company_projection`, migration 037). The row's `body` is the
   projection body, unchanged.
4. The trigger `publish_company_authority` rewrites each publication row
   (`company_payload_from_table`). It replaces each Company object with the
   dated row's `body`, which is the same body. It rebuilds an alias as
   `{entity_id, kind, canonical_id, status}`, which is the object the Merge
   Stage already sent (`merge.py`).
5. At delivery, `Store._company_output_from_table` rebuilds the Company
   objects from the table again, and checks the named columns against the
   selected fields.

Steps 4 and 5 produce the bytes they were given. Step 4 took 1,639 of the
1,796 seconds of Merge Stage database time in ticket 05's Proving Run. Its
loop copies the growing array on each append.

## Checklist (times ET)

- [x] `/gof-refactor-reviewer` on the Company write and read paths, before
  any code (2026-09-26 13:20 ET). **Verdict:** do B through one read seam.
  - Five readers each know where a current entity is stored. #714 had to
    touch them 18 hours ago, and B would touch four of them again.
  - The seam is one SQL view, `mdm_v2.current_entity (object_id, kind,
    status, canonical_id, body)`, made of `projection` entities, the open
    Company rows and the open alias rows. Every reader uses it, and none
    branches on kind. The single writer, `commit_batch_core`, routes by kind
    in one place.
  - The view stores nothing, so it adds no copy.
  - Expected cost: the snapshot's hash input changes, so a `ready`
    assessment stored before the migration would be assessed again.
    **Not so in the result:** the view's rows equal what `projection` held,
    so the snapshot is byte-identical and such an assessment still applies
    (proved by `test_migration_041_applies_to_a_populated_store`).
  - Not changed: review reads in `bookkeeping.py`.
- [x] Find every reader of Company rows in `projection`, in Python and SQL.
  Each one now reads `mdm_v2.current_entity`:
  - `binding.py`: the survivor and in-review checks;
  - `merge.py`: the "before" state kept with an assessment;
  - `cli.py`: the counts report;
  - `assessment_snapshot`, the hash of the scope;
  - the tests' `documents(..., "entity")`.
  - `consumer.py` needs no change. `entity()` always resolves a generation,
    so a Company is read from the Company table at that generation
    (`_company_at`). Its `projection` branch for `generation is None` is
    never reached from `entity()`.
- [x] Tests first (PostgreSQL 16), in `test_clean_company_one_place.py`.
  Each one failed on the code before this ticket:
  - a commit writes no Company to `projection`, and the Company table holds
    the body the Merge Stage computed;
  - a merged-away Company is only an alias row;
  - a Person stays in `projection`;
  - the copy steps are gone;
  - a publication carries the objects the Merge Stage computed
    (characterization: true before and after);
  - 041 applies to a populated store (below).
  - A stale assessment is still refused when a Company in its scope changes:
    covered by the existing assessment tests, which now read the view.
- [x] One new migration, `041_clean_mdm_company_one_place.sql`, restates each
  changed SQL function whole:
  - `commit_batch_core` sends a Company entity to
    `record_company_projection` (037) and everything else to `projection`;
  - `assessment_snapshot` reads entities from `current_entity`;
  - it drops the triggers `project_company_version` and
    `publish_company_authority`, and `company_payload_from_table`;
  - on a populated store, each Company row in `projection` is checked
    against the Company table, then removed.
- [x] Removed `Store._company_output_from_table`. Delivery sends the stored
  payload. With it went the delivery-time check of the named columns against
  the selected fields, and its two tests; the named columns are written from
  the same body in one function (037).
- [ ] Prove it on PostgreSQL 16:
  - [x] a store populated at 040, then migrated (Companies unchanged, the
    stored snapshot still matches, the assessment applies);
  - [ ] the full Clean suite. First run (2026-09-26 14:03 ET): 8 failures.
    Seven tests fill a store built at an older migration with today's code,
    which reads `current_entity` before 041 exists. Fix: the shared test
    helper gives such a store a stand-in view over `projection`, and 041
    uses `CREATE OR REPLACE VIEW` to replace it. The eighth counted views
    and now includes `current_entity`;
  - [ ] ticket 05's chunk 1 again, for the new timing.
- [ ] Three-axis `/code-review` (Standards, Spec, GoF), then PR and CI.

## Noted, not in scope

- **Named columns.** The Company table has 20 named columns (`cik`, `lei`,
  `name`, `sic`, and the `gleif_*` columns). Adding a field as a column means a
  migration plus an edit to the writer. Every selected field is also in
  `fields` (JSONB), which needs neither. The operator asked that new MDM
  fields be easy to add. The named columns were the operator's choice on
  2026-09-25 (ticket 09). Whether to keep them is the operator's call; this
  ticket does not change them.
- **Other kinds.** Person, Security and the rest still live in
  `projection`. They have no dated table.
