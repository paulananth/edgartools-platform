# Re-baseline the MDM schema as `mdm`, with business names and comments

Type: task
Status: in progress (Claude, branch `claude/mdm-rebaseline-slice3`)

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

- [ ] Dump the final schema of migrations 023–043 from a fresh PG16
- [ ] GoF consult on `store.migrate` and the save functions
- [ ] Build `001_mdm.sql`: renames, `write_batch`, generated per-kind
  views, comments on everything
- [ ] `store.py`: one baseline, new names in the grant list, refuse an
  `mdm_v2` store
- [ ] Every `mdm_v2` and old table name in `edgar_warehouse/`, `tests/`,
  `skills/`, `docs/`, `AGENTS.md`, `rules/`, and the scripts that will run
  (`27_proving_run.py`, the round-2 Person trial)
- [ ] Comment-coverage test: every table, column, view and function in
  `mdm` has a comment
- [ ] Fresh PG16 from zero: only `mdm`, no `mdm_v2`, no `public.mdm_*`
- [ ] Unit and MDM tests; each integration file under 5 minutes
- [ ] Ticket 27 Proving Run on the new schema: same counts (6,414
  Companies, 3,052 with CIK and LEI, second pass unchanged)
- [ ] Three-axis `/code-review`
- [ ] PR, CI green, merge on the operator's word
- [ ] Recreate the operator's `edgartools-clean-mdm-pg16`: only on their
  word, after merge
