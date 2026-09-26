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

- [ ] `/gof-refactor-reviewer` on the Company write and read paths, before
  any code.
- [ ] Find every reader of Company rows in `projection`, in Python and SQL,
  and write down how each one reads the Company table instead. Known so far:
  - `binding.py`: status, survivor and review checks;
  - `merge.py`: the "before" state kept with an assessment;
  - `consumer.py`: the read API;
  - `cli.py`: the counts report;
  - `assessment_snapshot` (028), the hash of the scope;
  - the tests that read `documents(..., "entity")` for a Company.
- [ ] Tests first (PostgreSQL 16). Each one fails on today's code:
  - a commit writes no Company to `projection`;
  - the Company table holds the same current body the Merge Stage computed;
  - a merged-away Company appears only in `company_alias`;
  - a publication's objects equal the batch's computed objects, with no
    rewrite;
  - a stale assessment is still refused when a Company in its scope changes.
- [ ] One new migration restates each changed SQL function whole, not by
  text edit:
  - `commit_batch_core` writes a Company entity to the Company table, and
    everything else to `projection` as before;
  - `assessment_snapshot` hashes Companies from the Company table;
  - it drops the triggers `project_company_version` and
    `publish_company_authority`, and `company_payload_from_table`;
  - a populated store moves its Company rows out of `projection` (the
    Company table already holds them, from 037's backfill).
- [ ] Remove `Store._company_output_from_table`. Delivery sends the stored
  payload.
- [ ] Prove it on PostgreSQL 16:
  - the full Clean suite;
  - a store populated before the migration;
  - ticket 05's chunk 1 again, for the new timing.
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
