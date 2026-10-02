# Re-baseline the MDM schema as `mdm`, with business names and comments

Type: task
Status: resolved: merged in #767. The old pg16 store was deleted on 2026-10-02 at the operator's word, with a backup (2026-10-02 audit, mastering to-do 01).
Was: in progress (Claude, branch `claude/mdm-rebaseline-slice3`)

## Operator rulings (2026-09-30)

- "make mdm_v2 to mdm".
- Table names: "Rename all as proposed":
  - `assertion` → `source_reading`
  - `identity` → `master_entity`
  - `projection` → `current_record`
  - `observation` → `run_batch`
  - `assessment(_event)` → `match_proposal(_event)`
  - `deferred_record` → `set_aside_record`
  - `publication(_event)` → `outbox(_event)`
  - `commit_batch_core` + `commit_batch` → `save_batch`
- "make the table self explainable": every table, column, view and
  function carries a plain-English `COMMENT ON`.
- "continue with slice 3 complete testing and creating person" (2026-09-30).

## Decisions taken here (no ruling needed; stated in the PR)

- **One baseline file.** Migrations 023–043 become one
  `001_mdm.sql`, built from the final migrated schema (`pg_dump -s`), not
  from replaying 21 files. There is no production to keep, and several old
  migrations edited function bodies by regex, which a reader cannot follow.
- **Tables are renamed; columns are not.** Columns such as `assertion_id`,
  `deferred_id` and `assessment_id` are also the JSON keys of the requests
  Python builds, so renaming them would change every payload. Each one's
  comment says what it holds in the new vocabulary.
- **Names that contain a renamed table follow it**: functions
  (`record_assessment` → `record_match_proposal`, `claim_publication` →
  `claim_outbox`, …), constraints and indexes. The `clean_` prefix is
  dropped from index names: there is no other MDM.
- **`save_batch`.** `commit_batch` becomes `save_batch`, the one function
  the runtime calls to save a batch. `commit_batch_core` and
  `commit_batch_evidence` merge into one internal `write_batch`, which
  `save_batch` calls after its match-proposal check. They cannot all be one
  function: `preview_batch` must run the writes without that check (it
  previews a batch before a proposal exists) and roll them back.
- **The per-kind views stay generated** from the kinds `master_entity`
  permits, so a new kind does not mean copying views.
- **An old store is refused.** `mdm migrate` fails, with a clear message,
  on a database that still has an `mdm_v2` schema, instead of installing
  `mdm` beside it.

## Checklist

- [x] Dump the final schema of migrations 023–043 from a fresh PG16
  (2026-09-30 22:05 ET)
- [x] GoF consult on `store.migrate` and the save functions: leave the
  structure; drop `FUNCTION_MIGRATION` (2026-09-30 22:10 ET)
- [x] Build `001_mdm.sql`: renames, `write_batch`, generated per-kind
  views, comments on everything. Structural diff against the old schema
  (renames applied): every table, key, reference, index, trigger and view
  identical; only the intended functions differ (2026-09-30 22:45 ET)
- [x] `store.py`: one baseline, `RUNTIME_FUNCTIONS` with the new names,
  refuses an `mdm_v2` store (test) (2026-09-30 23:00 ET)
- [x] Every `mdm_v2` and old table name in code, tests, skills, docs and the
  two scripts that run. Dated reviews keep their names, with a note
  (2026-09-30 23:10 ET)
- [x] Comment-coverage test: `test_mdm_schema_comments.py`, 4 passed
  (2026-10-01 00:12 ET)
- [x] Fresh PG16 from zero: only `mdm` (21 tables, 33 views, 20 functions),
  no `mdm_v2`, no `public.mdm_*` (test)
- [x] Unit, MDM and architecture tests: 1,123 passed. Each MDM integration
  file under 5 minutes: 16 files, all passed after two test fixes
  (a `source_*` pattern that now matched `source_reading`; a test of the
  deleted 033 kind-list guard, replaced by "every kind has its views")
  (2026-09-30 23:40 ET)
- [x] Ticket 27 Proving Run on the new schema: 6,414 Companies, 3,052 with
  CIK and LEI, second pass unchanged; every count in the report equals the
  pre-slice-3 report. **Took 19 min 10 s** (2026-10-01 00:05 ET)
- [x] Three-axis `/code-review` (2026-10-01 00:30 ET): GoF "leave it" (the
  merge removes the axis that changed in 14 of 17 old migrations);
  Standards: three comments corrected, Company checks and two indexes
  renamed, a populated-store migrate test added; Spec: living specs and the
  Proving Run script renamed, a fresh-store `stage_waiting` test restored
  (the deleted 036 test was its only database check). Database error
  messages keep their wording: callers and tests match on it.
- [ ] PR, CI green, merge on the operator's word
- [ ] Recreate the operator's `edgartools-clean-mdm-pg16`: only on their
  word, after merge
