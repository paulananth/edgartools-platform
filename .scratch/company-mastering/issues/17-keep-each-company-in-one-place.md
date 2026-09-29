# Keep each Company in one place

Type: task
Status: built and reviewed; PR (Claude, branch `claude/company-mastering-17-company-one-place`)
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
    (proved by `test_migration_042_applies_to_a_populated_store`).
  - Not changed: review reads in `bookkeeping.py`.
- [x] Find every reader of Company rows in `projection`, in Python and SQL
  (2026-09-26 14:09 ET; verified by a repo search and by the Spec and GoF
  reviews, 14:25 ET). Each one now reads `mdm_v2.current_entity`:
  - `binding.py`: the survivor and in-review checks;
  - `merge.py`: the "before" state kept with an assessment;
  - `cli.py`: the counts report;
  - `assessment_snapshot`, the hash of the scope;
  - the tests' `documents(..., "entity")`.
  - `consumer.py` reads a Company at a generation from the Company table
    (`_company_at`, `snapshot_page`), which a view of the current state
    cannot serve. Its `_object` had a `projection` branch for
    `generation is None` that `entity()` never reaches; it would have missed
    every Company, so it is deleted (review, 14:27 ET).
  - Not switched: `.scratch/source-contract/prototype/engine/merge_harness.py`
    reads all of `projection`. It is a throwaway prototype, not on any
    production or Proving Run path.
- [x] Tests first (PostgreSQL 16), in `test_clean_company_one_place.py`
  (2026-09-26 14:09 ET). On the code before this ticket, four failed (the
  commit, alias, copy-steps and migration tests) and two passed by design
  (the Person and publication tests, which pin behaviour that must not
  change). All pass now:
  - a commit writes no Company to `projection`, and the Company table holds
    the body the Merge Stage computed;
  - a merged-away Company is only an alias row, and the as-of read builds
    the same alias object (added after review, 14:28 ET);
  - a Person stays in `projection`;
  - the copy steps are gone;
  - a publication carries the objects the Merge Stage computed
    (characterization: true before and after);
  - a Company change alone changes the assessment snapshot, so a stale
    assessment is refused (added after review, 14:28 ET: the existing
    assessment tests also change evidence, so they could not show this).
    Red on main's code (2026-09-26 14:36 ET): the snapshot was identical
    before and after the change, because it read `projection`;
  - 042 applies to a populated store (below);
  - 042 refuses to remove a Company in `projection` that differs from the
    Company table, and changes nothing (added after review, 14:28 ET).
- [x] One new migration, `042_clean_mdm_company_one_place.sql`, restates each
  changed SQL function whole (2026-09-26 14:09 ET; verified by the Standards
  review against 023 + 028 + 029 + 031, 14:24 ET):
  - `commit_batch_core` sends a Company entity to
    `record_company_projection` (037) and everything else to `projection`;
  - `assessment_snapshot` reads entities from `current_entity`;
  - it drops the triggers `project_company_version` and
    `publish_company_authority`, and `company_payload_from_table`;
  - on a populated store, each Company row in `projection` is checked
    against the Company table, then removed.
- [x] Removed `Store._company_output_from_table` (2026-09-26 14:09 ET;
  verified by the publication test). Delivery sends the stored payload. With
  it went the delivery-time check of the named columns against the selected
  fields, and its two tests. The named columns are written from the same
  body in one `INSERT` (037, `record_company_projection`).
- [x] Prove it on PostgreSQL 16 (2026-09-26 14:49 ET):
  - [x] a store populated at 040, then migrated
    (`test_migration_042_applies_to_a_populated_store`, 2026-09-26 14:30 ET).
    Companies read back unchanged. The stored assessment covers Apple's
    existing Company, its snapshot still matches, and it applies.
  - [x] the full Clean suite: **200 passed** (2026-09-26 14:48 ET, 17 min,
    on the code with the review fixes). First run (14:03 ET, 23 min):
    8 failures. Seven tests fill a store built at an older migration with
    today's code, which reads `current_entity` before 042 exists. Fix: the
    shared test helper gives such a store a stand-in view over `projection`,
    and 042 uses `CREATE OR REPLACE VIEW` to replace it. The eighth counted
    views and now includes `current_entity`.
  - [x] ticket 05's chunk 1 again, for the new timing (2026-09-26 14:49 ET,
    same 966 records, same bundle, same candidate policy, harness from the
    ticket 05 branch, not committed here): **24.0 s**, against 395.6 s and
    564.9 s for the two earlier runs of the same chunk. Every outcome is
    identical to the earlier run: 919 Companies, 919 bindings, 47 deferred
    reviews, no CIK on two Companies, and the second pass changed nothing.
    Largest database cost now: `commit_batch_core`, 9.9 s in total over both
    passes; `company_payload_from_table` no longer exists.
- [x] Three-axis `/code-review` (Standards, Spec, GoF), 2026-09-26 14:26 ET.
  Fixed: the 042 header named the wrong migrations; the Company spec line
  (`company-completion.md`); the untested 042 check; the dead `consumer.py`
  branch; the private-method assertion; the stale-assessment test. Kept, with
  reasons in the PR: `CREATE OR REPLACE VIEW` for the test stand-in; the
  alias object built in three places (now pinned by tests).
- [x] Rebased onto main (2026-09-29): ticket 13 took migration 041, so this
  one is **042**; every reference renumbered. Ticket 13's migration changes
  only `release_binding` and `keep_stage`, not the functions 042 restates.
  Conflicts: the migration list (both kept), the counts report (main's
  `handle`, with this ticket's `current_entity` read), and the delivery-time
  rebuild (removed, as here; ticket 13's quarantined check went with it, and
  037 still writes the column from the same body). Ticket 13's PG16 tests
  pass on this branch (22 with this ticket's).
- [x] Timed again on synthetic data (2026-09-29, `research/17_batch_timing.py`;
  ticket 05's bundles are gone): one batch of 960 new Companies takes
  **10.1 to 10.8 s** here against **37.3 to 42.3 s** on main; a revision of
  all 960 takes **4.1 to 4.2 s** against **16.9 to 17.6 s**.
- [x] Full suite on the rebased branch (2026-09-29): 3,111 passed, 1 xfailed, in 7:27.
- [ ] PR and CI.

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
