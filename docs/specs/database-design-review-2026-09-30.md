# Database design review, 2026-09-30

> **Applied (platform validation slice 3):** the schema is now `mdm`, re-baselined as one migration (`001_mdm.sql`) with the names ruled below and a comment on every object. This review keeps the names as they were when it was written.

Validation slice 1 (`.scratch/platform-validation/`). This review reads the code and migrations of the four PostgreSQL 16 databases the rebuilt platform uses. It lists every table and says what it is for. It shows how the databases hand work to each other, sets the three operator skills side by side, and ranks what should change. Every finding names a file. Nothing here changes a database.

## The four databases

The four are separate databases, which can share one PostgreSQL 16 server. Each one checks, when it is created, that it has the name it expects and runs on version 16. Each has an owner that cannot log in, and a login for the application that may only call functions or write named columns.

| Database | Schema | Holds | Created and migrated by | Migrations |
|---|---|---|---|---|
| `rules` | `rules` | Every version of every rules file: sources, merge rules, pipelines. Also their test runs and approvals. | `edgar-warehouse rules init` (running it again migrates) | `edgar_warehouse/rules/migrations/`, 001–003 |
| `bookkeeping_clean` | `bookkeeping` | Runs, their work items, leases, checkpoints and the outbox to the Journal | `edgar-warehouse bookkeeping init` / `migrate --runtime-role` | `edgar_warehouse/bookkeeping/clean/migrations/`, 001–004 |
| each destination database | `bookkeeping_guard` | Which run may write which resource | `bookkeeping init-guard` | `destination_guard.sql` |
| `change_journal_clean` | `journal` | The append-only record of what was acquired and published | `edgar-warehouse change-journal init` / `migrate --runtime-role` | `edgar_warehouse/change_journal/migrations/`, 001 |
| `mdm` | `mdm_v2` | Clean MDM: source readings, master entities, decisions, the approved policy | `edgar-warehouse mdm migrate --model clean --application-role …` | `edgar_warehouse/mdm/migrations/`, 023–042 |
| `mdm` (same database) | `public` | **Legacy MDM**, 27 tables. Nothing enabled uses them. | `mdm migrate --model legacy` | the same folder, 001–022 |

## Every table

### Clean MDM (`mdm_v2`)

None of these tables, columns or functions has a database comment today (`COMMENT ON` appears in no migration), so `\d+` explains nothing. Slice 3 adds a comment to each, and may rename the unclear ones (see "Names" below).

| Group | Table | What it holds | Written by | Read by |
|---|---|---|---|---|
| Master data | `identity` | One row per master entity (a Company, a Person…) and its kind | `commit_batch_core` | Merge Stage, views |
| | `company` | Each Company, versioned over time. Since 042 a Company is written here only. | `record_company_projection` | `current_entity`, the `company_*` views |
| | `company_alias` | Old Company ids that now point to another | `record_company_projection` | `current_entity` |
| | `projection` | The current record of every other kind, plus relationships and review items | `commit_batch_core` | `current_entity`, `stage_waiting`, per-kind views |
| | `stage_record` | Each source record's latest reading and the entity it is joined to | `record_stage`, `record_binding` | Merge Stage (binding, matching), per-kind `_stage` views |
| | `decision` | Each join, merge, reversal, override or exclusion, and the rule or person that made it | `commit_batch_core` | Merge Stage, correction |
| Source evidence | `assertion` | Every version of every source record as read; never changed | `commit_batch_core` | Merge Stage, `stage_record` |
| | `deferred_record` | Records set aside, and why (not a Company, invalid field, waiting for a match) | `commit_batch_evidence` | `stage_waiting` |
| Rules | `policy` | Each Mastering Policy by fingerprint, as approved | `register_policy` (via `rules activate`) | Merge Stage |
| | `dataset` | Each source code and its registry authority | `register_dataset` | batches, adapters |
| | `dataset_mapping` | Each version of how a source is read | `register_dataset` | Merge Stage, `stage_record` |
| Support | `batch` | Each saved batch: its hash, run, policy and generation | `commit_batch_core` | duplicate checks, checkpoints |
| | `observation` | Which run saw which batch | `commit_batch_core` | run reconciliation |
| | `checkpoint` | How far each reader (consumer) has read | `commit_batch_core` | the next batch's check |
| | `attempt_event` | Each try at a batch: started, committed, failed | `record_attempt` (run coordinator) | recovery |
| | `assessment`, `assessment_event` | Proposed matches checked before they are saved, and what became of them | `record_assessment`, `supersede_assessment` | Merge Stage |
| | `publication`, `publication_event` | What must be sent on (Journal, exports), and its delivery | `commit_batch_core`, `claim/finish_publication` | publishers, `change-journal recover mdm` |
| | `migration` | Which migration files are applied, with checksums | `store.migrate` | `store.migrate` |

The views are:
- `current_entity`: the one read of a current entity.
- `stage_waiting`: records waiting for review.
- One set per kind, generated by 033/034: `<kind>_stage`, `<kind>_stage_field`, `<kind>_master` and `<kind>_master_field`.

**`commit_batch_core`.** This is the one function through which every Merge Stage write is saved. In one transaction it:
1. Refuses a batch that is:
   - over 16 MiB, or holds more than 1,000 records, 1,000 decisions or 10,000 current records;
   - a reused batch id with different content;
   - a stale generation or a checkpoint that does not advance;
   - from a source whose reading is not registered.
2. Records the batch and which run saw it.
3. Saves each source reading, new entity and decision.
4. Updates the current records: Companies go to `company`, everything else to `projection`.
5. Advances the reader's checkpoint and queues what must be published.

It exists so a batch is saved whole or not at all, and so the application login needs no table rights. `commit_batch` is a thin wrapper around it.

### Rules (`rules`)

| Table | What it holds |
|---|---|
| `rule_version` | One row per version of a source, merge or pipeline rules file. It holds the body and its digest, its test run (`proof`, `batch_hash`), its approval (`approved_by`, `approved_words`, `approval_overrule`, `approval_evidence`, `approval_recorded_by`) and its status: draft, then proven, then active, then retired. The trigger `govern_version` enforces the lifecycle: content never changes, no approval without a test run, an approval is never changed. `govern_acquisition` (002) governs acquisition feeds. |

### Bookkeeping (`bookkeeping`, `bookkeeping_guard`)

| Table | What it holds |
|---|---|
| `pipeline_run` | One run of a configured source and feed, with its frozen rules reference and inputs |
| `work_item` | Each unit of work in a run: step, state, receipt |
| `lease` | Who is working on an item now, and until when |
| `checkpoint` | Each resource's last committed position (002) |
| `journal_outbox` | Events waiting to be delivered to the Journal |
| `bookkeeping_guard.resource` | In each destination database: which run may write a resource |

### Change Journal (`journal`)

| Table | What it holds |
|---|---|
| `event` | Append-only: each acquisition, source evidence and publication event, with its receipt. An immutability trigger refuses change. |

### Legacy MDM (`public`, 27 tables)

These are created by migrations 001–022 and never dropped. Nothing enabled writes them. `mdm counts`, one of the five `mdm` commands still enabled, reads them and fails on a Clean-only database (finding 4).

| Legacy tables | Were for |
|---|---|
| `mdm_entity`, `mdm_company`, `mdm_person`, `mdm_fund`, `mdm_security`, `mdm_adviser`, `mdm_audit_firm` | Legacy master records |
| `mdm_source_ref`, `mdm_entity_attribute_stage`, `mdm_entity_type_definition`, `mdm_change_log` | Legacy source links, staging, kinds and change log |
| `mdm_match_review`, `mdm_match_threshold`, `mdm_normalization_rule`, `mdm_source_priority`, `mdm_field_survivorship` | Legacy matching and survivorship rules, now replaced by the Rules DB and `rules/merge/` |
| `mdm_relationship_type`, `_instance`, `_property_def`, `_source_mapping`, `_source_priority`, `_coverage`, `_derivation_checkpoint` | Legacy relationships |
| `mdm_graph_generation`, `mdm_graph_partition`, `mdm_publication_request`, `mdm_pipeline_lease` | Legacy graph publishing and leases |

The legacy Bookkeeping store, with 10 tables in `edgar_warehouse/bookkeeping/models.py`, is retired (`bookkeeping/database.py` raises). Its models are still imported by 6 modules, including the Clean MDM `RunCoordinator` (finding 2).

## How the databases hand work to each other

No transaction spans two databases. Each handoff is a recorded receipt that can be retried.

| From → to | How | Recovery |
|---|---|---|
| Rules → MDM | `rules activate` registers the approved policy and readings in `mdm_v2` (`register_policy`, `register_dataset`, via `RULES_MDM_ACTIVATION_DATABASE_URL`) and records the handoff receipt (`clean_mdm`) on the rule version | Activate again. Registration is idempotent. |
| Rules → Bookkeeping | `rules run` freezes the active rules reference into a new run | `bookkeeping resume <run>` |
| Bookkeeping → Journal | `bookkeeping.journal_outbox`, delivered to `journal.event` | `change-journal recover bookkeeping <run>` |
| MDM → Journal | `mdm_v2.publication`, delivered to `journal.event` | `change-journal recover mdm <batch> --worker` |

## The three skills' modes

| Mode | Bookkeeping | Change Journal | Rules (to become Data Onboarding + Refining Rules) |
|---|---|---|---|
| init | `bookkeeping init --runtime-role` | `change-journal init --runtime-role` | `rules init` |
| migrate | `bookkeeping migrate --runtime-role` | `change-journal migrate --runtime-role` | `rules init` again. **`rules migrate` is a different thing** (it moves rules between files and the database), which is a naming trap. |
| init a destination | `bookkeeping init-guard` | — | — |
| plan | `bookkeeping prepare` | `run_mode.py plan … --output` | "Add a source", steps 1–7 |
| validate | against approved rules and captured manifests | `run_mode.py validate` | steps 8–9: `rules check` and Preview, **not built** |
| deploy / run | `rules run`, then `bookkeeping runs/status/checks/leases/resume <run>` | `run_mode.py deploy` | step 10: `rules save`, `record-proof`, `approve`, `activate`, `run` |
| approve | — | — | `rules pending`, `rules approve` |
| change, quality, metadata | — | — | `rules mapdoc diff/write/check`, `quality.yaml`, `rules catalog publish` |
| recover | `bookkeeping resume` | `recover bookkeeping`, `recover mdm` | — |
| status | `bookkeeping runs`, `status <run>` | `status`, `events`, `verify` | `rules status --source` |

The proposal is one vocabulary, used in the same order in every skill, with one owner per mode:
- **run a feed**: Bookkeeping, even though `rules run` appears in two skills;
- **recover a Bookkeeping run**: Bookkeeping;
- **recover MDM delivery**: Change Journal;
- **run mastering**: a named skill (finding 3).

The operator rules on the names.

## Findings

| # | Severity | Finding | Evidence | Recommendation | Slice |
|---|---|---|---|---|---|
| 1 | High | Legacy MDM, 27 tables and 34 modules, lives in the same database and migration folder as Clean MDM, and nothing enabled uses it | `mdm/migrations/001–022`, `edgar_warehouse/mdm/*.py` | Delete the code, the migrations and the tables (local databases recreated; a hosted database only on the operator's word) | 2 |
| 2 | High | The Clean MDM run coordinator needs the retired Bookkeeping models. Ticket 27 had to skip its start and reconcile. | `mdm/clean/bookkeeping.py` imports `PipelineRun`, `BookkeepingStore` | Move the root run to MDM's own `attempt_event`, or to `bookkeeping_clean`, then delete the legacy models and their 6 importers | 2 |
| 3 | High | No enabled command runs mastering. The Merge Stage is reached only by `bookkeeping/clean/mdm_capabilities.py`, tests and scripts. `mdm apply-decisions` is advertised but blocked, and has no handler. | `edgar_warehouse/cli.py main()`, `mdm/clean/cli.py handle()` | One path: Bookkeeping's `mdm` target through `rules run --target mdm`, named in a skill | 4 (ticket) |
| 4 | Medium | `mdm counts` is enabled but reads legacy tables, so it fails on a Clean-only database | walk-through, 2026-09-30 | Rewrite it on `mdm_v2` (per-kind counts) or disable it | 2 |
| 5 | Medium | The 16 MiB batch cap is below real GLEIF batches (1,000 records came to 43 MB) | ticket 27 | Keep the cap. Size GLEIF batches by bytes in the code that builds them. | ticket |
| 6 | Medium | The Name Census refuses a capture with no former names, although the landing writer skips empty tables by design | ticket 27 | Treat a missing former-name member as none | ticket |
| 7 | Medium | No table, column or function has a database comment. Several names do not say what they hold (`assertion`, `identity`, `projection`, `observation`, `assessment`). | migrations 023–042 | Comment every object. Rename on the operator's ruling (below). | 3 |
| 8 | Medium | The schema is called `mdm_v2` although there is no other system to be version 2 of | all Clean MDM code | Re-baseline Clean migrations under schema `mdm` | 3 |
| 9 | Low | `rules migrate` does not migrate the Rules Database: `rules init` does. The other two stores use `migrate` for that. | `rules/cli.py` | Name the file↔database move something else (e.g. `rules load` / `rules unload`) | 4 |
| 10 | Low | The rules skill cites `COMPANY_NAMED_FIELDS` (it does not exist) and `CHANGE_LEDGER_DATABASE_URL` (`rules activate` does not read it) | `skills/rules/SKILL.md` | Fix in the skill split | 4 |
| 11 | Low | Migration history is kept differently: a schema comment with checksums (rules, bookkeeping, journal) versus a `migration` table (MDM) | the four `*/database.py` and `store.py` | Keep both for now. Note it in the comment standard. | — |

## Names (for the operator to rule on before slice 3)

| Today | Proposed | Why |
|---|---|---|
| `mdm_v2` | `mdm` | There is one system |
| `assertion` | `source_reading` | It is a source record as read |
| `identity` | `master_entity` | It is the master entity |
| `projection` | `current_record` | It is the current record of an entity, relationship or review |
| `observation` | `run_batch` | It says which run saw which batch |
| `assessment`, `assessment_event` | `match_proposal`, `match_proposal_event` | A proposed match, checked before saving |
| `deferred_record` | `set_aside_record` | A record set aside, with its reason |
| `publication`, `publication_event` | `outbox`, `outbox_event` | What must be sent on, and its delivery |
| `commit_batch_core` + `commit_batch` | `save_batch` | Saves one batch of Merge Stage work, whole or not at all |
