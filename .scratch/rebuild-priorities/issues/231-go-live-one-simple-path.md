# 231: Go-live: one simple path from a source to MDM, RDM and silver

Priority: 231. Map: [Rebuild priorities](../map.md). Opened 2026-11-12 07:52 ET (operator: "remove any refrences to migration as we are planning to go-live, remove any old conepts ... remove 7 wastes with out losing functionality ... all rules and configuration must be able to be assembled by hand or agent without proving runs and multiple approvals, remove repeated validations ... it has been complicated to death goal is to simiplify and make it clean").

Type: task. Status: open.

## The target

Select a source, extract it, identify its master data and master it in MDM. Pre-merge data stays in the
Merge Stage, the golden record stays in MDM, codes go to RDM, relationships are inferred, and every detail
goes to silver. Rules and configuration are files a person or an agent assembles by hand.

## The operator's rulings (2026-11-12 07:52 ET)

1. **Rules gates: "Files are the rules".** A run reads the rules files in git after one offline check
   (`rules check`). Proof, approval, activation, `rules/approvals.yaml` and `rules/merge/pending-proofs.yaml`
   go. The Rules Database only records which rules digest each run used.
2. **Run checks: "Worker checks its own step".** The separate verifier duty and the re-verification of
   earlier steps go. Each step checks its own result once and Bookkeeping records it so a stopped file resumes.
3. **Schema files: "One schema file, keep upgrades".** Each store's numbered files fold into one current
   schema that `init` creates; the upgrade command stays for a schema change after go-live.
4. **After silver: remove** Neo4j, the dashboards, Snowflake gold and dbt, and the old planning and handoff
   files ("we need to build agentic data layer, and possibly gold and dashboards later").
5. **History: "this is version 1.0 so no history"** (operator, 2026-11-12). Nothing in the code, tests, rules,
   skills or documents tells what came before: no earlier digest, no answer read through an undo of a later
   ticket, no ticket number or date in a comment, no refusal that names an older schema or stage.

## Checklist

Each part is its own branch and PR, in this order (remove first, then simplify what is left).

- [x] (2026-11-12 07:52 ET) Old planning and handoff files removed: `.planning` (766 files), `TODOS.md`, the handoff, release-readiness and internal session documents, `scripts/claim-workstream.sh` and 121 closed folders under `.scratch`. Kept: this ticket folder, the four folders changed since 2026-11-10 and `.scratch/company-mastering`, which a test reads until the rules-gates part. Verified by the guide-path, skill and stamp lints (143 tests pass)
- [ ] Dated research, design-report and decision documents under `docs/` that describe an older stage: read each, keep what the simple path uses
- [x] (2026-11-12 08:12 ET) Neo4j removed: its document, grants and secrets notes. `Dockerfile.mdm-neo4j` was the live MDM image under an old name, so it is renamed `Dockerfile.mdm` (publish script, skill and test updated), not deleted. Verified by `tests/architecture/test_rules_files_ship.py`
- [x] (2026-11-12 08:12 ET) Dashboards removed: the Streamlit app and its deploy script, `edgar_warehouse/serving`, `examples/dashboard`, the dashboard acceptance scripts, their six test files and their documents. Verified by the unit and architecture tests
- [x] (2026-11-12 08:12 ET) Snowflake gold and dbt removed: the dbt project (85 files), the gold SQL (34), the Snowflake Terraform roots, access roots and templates, `deploy-snowflake-stack.sh`, the `resolve-snowflake-env` command with `snowflake_settings.py`, the `snowflake` extra and its lock entries, and the documents and decision records of the gold, decision-contract and retired AWS pipelines. Kept: `infra/snowflake/postgres` (the hosted MDM store). `CLAUDE.md`, `AGENTS.md`, `README.md` and the `aws-snowflake-operations` skill say the platform ends at silver. Verified by the unit and architecture tests, the guide-path lint and the skills' link check
- [ ] What is still deployed: the Snowflake account's gold objects and tasks, and the AWS resources that fed them (the export bucket, its KMS key and SNS topic, the `dbt/snowflake` and `mdm/snowflake` secrets, with their Terraform, `secrets-manifest.json`, `preflight-prod-promotion.sh` and `docs/agents/aws.md` lines). Removing them changes live accounts: it needs the operator's word and a Terraform plan
- [ ] The README's processing and work-control diagrams redrawn once the rules gates and run checks are simplified
- [ ] Rules gates: a run reads the checked rules files; proof, approval and activation deleted, with their commands, tables and files. In three PRs:
  - [x] (2026-11-12 12:04 ET) A1, the run: `rules run` builds its frozen rules from the files (kind, name, digest, body) after `rules check`; Bookkeeping's run start and the acquisition, processing and registration authorities ask for the digest only; the source's Dataset Contracts and the merge rules are registered in MDM by the load itself, before it prepares; the Rules Database is one table of the digests runs used. Deleted: `rules save`, `export`, `record-proof`, `approve`, `activate`, `pending`, `approvals`, `load`, `unload` and `test`, `approvals.py`, `proving.py`, `rules/approvals.yaml`, the lifecycle trigger and the approver role. Verified: unit, architecture and MDM tests, `tests/engine` (955 pass), `tests/integration` on PostgreSQL 16, `tests/storage_adapters` on PostgreSQL and MySQL (162 and 171 pass)
  - [x] (2026-11-12 12:30 ET) A2, the merge rules: a rule listed under `automatic_rules` is on; an entry names kind, family, rule, version and verdict only. Gone: the proof blocks, the bars and accepted bars, the Identifier Contracts' verification and tolerance blocks, `rules/merge/pending-proofs.yaml`, `rules approve`, the Wilson-bound check and the approval-lineage tests (`tests/mdm/policy_layers.py` keeps `with_rules_on`). Kept: every rule's well-formedness check and the Identifier Contract an identifier rule needs. Verified: `rules check` and `rules mapdoc check` pass; unit, architecture and MDM tests; the six integration files that switch rules on (47 pass)
  - [ ] Left for the Words and documents parts: `"bars"` in the Rust kind-block key list (`crates/source-contract/src/field_values.rs`), the proof sections of `docs/specs/mdm/policy-language.md` after §9, the contract-digest lineage in `tests/mdm/test_rules_config_digests.py`, and `.scratch/company-mastering` (two tests and three documents still name it)
  - [ ] A3, the skills: onboarding and refining a source is assembling its files, `rules check`, then `load`; the test-run and approval steps and their pages go
- [x] (2026-11-12 15:10 ET) Run checks: a unit goes pending, running, verified. The worker checks what it wrote once (`check` in each worker module) and its report completes the unit. Gone: the `reported` state, the verifier role and login, `workers verify`, `bookkeeping verifications` and `admit`, `verifier.env`, the 5% redo sample, and the re-check of completed units on resume and finalize. Kept: leases and fencing, the pinned worker runtime, the receipt with its check report, the hash check of every input a step reads. Verified: unit, architecture, MDM and engine tests (3,355 pass); every integration file on PostgreSQL 16; `tests/storage_adapters` on PostgreSQL and MySQL
  - [x] (2026-11-12 16:45 ET) `skills/data-operations/SKILL.md` and its `RUNBOOK.md` no longer name `workers verify`, a verifier login or one verifier a run (the edit waited for Codex's PR 1714, now merged). Verified by the skill and guide-path lints
  - [ ] Left for the skills and words parts: "verifier" in prose of `skills/data-platform/READING.md`, `COMBINING.md`, `skills/data-operations/RUNBOOK.md`, `skills/mdm-engineering`, and in the "verifier byte budget" error texts
- [ ] Schema files: one current schema file per store; `init` creates it; the upgrade command kept
  - [x] (2026-11-12 15:10 ET) Bookkeeping: `migrations/schema.sql` replaces ten numbered files (and `mysql-v1.sql` is edited in place). A store built from it dumps the same as one built from the ten files plus the run-checks change (`pg_dump -s`, compared; the only difference is the grants on the new function). `migrate` applies it, then any numbered file added later; a store on the earlier files is refused with "rebuild the store"
  - [x] (2026-11-12 16:52 ET) RDM, the Change Journal, MDM and silver on PostgreSQL: each store's numbered files are one `migrations/schema.sql` (MDM 30 files, RDM 5, the Change Journal 2, silver 1), applied by `migrate` before any numbered file added later; a store on the earlier files is refused with "rebuild the store". MDM's registration rights are `registration_authority.sql`, and the routine-retirement module went with the files it retired. Verified by dumping a store built each way (`pg_dump -s`): the Change Journal is identical, RDM differs by brackets in one view, MDM by the applied-file record only (36 views, 2 functions, 25 tables, 75 indexes, 15 triggers each way); and by the unit, architecture, MDM, engine, integration and storage-adapter tests
  - [ ] RDM on MySQL: `mysql-v1.sql` and its three follow-up files (`mysql-search-v2`, `mysql-value-v3`, `mysql-properties-v4`) fold into one file
  - [ ] The Change Journal's native-storage statements (applied in code under the key `003_native_storage`) fold into its schema file
- [ ] Words: no reference to a migration from an older system, a legacy path, a cutover or a retired stage in the code, rules, guides, documents and skills
  - [x] (2026-11-12 17:05 ET) Code and tests, the word "legacy": refusals, help texts and docstrings say what the code does today; the engine catalog's two keys are `default_jurisdiction_table` and `default_pair_comparison`; tests that only checked deleted commands and deleted modules stay deleted are removed (`test_retired_commands_stay_unavailable`, the `gold-refresh` lines, `test_retired_submission_loaders.py`). Verified by the unit, architecture and MDM tests
  - [x] (2026-11-12 17:05 ET) Store refusals: MDM no longer looks for an `mdm_v2` schema (check and test removed); every store that is not on this build's schema says "does not hold this build's schema; rebuild the store". Verified by `tests/integration/test_mdm_schema_comments.py` and `test_bookkeeping_read_upgrade_postgres.py`
  - [ ] `mdm migrate --prepared-store` and the `prepared` argument: only one value is accepted, so the switch goes (it reaches the storage adapter scripts)
  - [ ] Ticket numbers, dates and "before/after" notes in code and test comments (ruling 5)
  - [ ] Answer files compared through an undo of later tickets: `tests/engine/retired_mapper_outcomes.json` (read through `before_ticket_129`, `old_words`, `before_ticket_10`, `historical_assertion`) and the chain of earlier digests in `tests/mdm/test_rules_config_digests.py` with `retired_mapping_lists.json`. Record today's answers once, see each fail once, delete the undo helpers
  - [ ] The catalog publisher's `retired_pipeline_service` clean-up and the "legacy" results file wording in `skills/openmetadata`: OpenMetadata is Codex's, so it is named here, not edited
  - [ ] Deployed-resource history in code: the DuckDB expiry rules in `storage_buckets/main.tf`, the secret moves that `test_mdm_snowflake_postgres_cutover.py` checks, `preflight-prod-promotion.sh` and its two tests, `warehouse_legacy_bucket_arn` in `create-deployer.sh`. They go with "What is still deployed" (a Terraform plan)
  - [ ] Skills: `bookkeeping/SPEC.md`, `change-journal/SPEC.md` and `INDEPENDENCE.md`, `bookkeeping/RECOVERY.md` and `RUN.md`, `data-platform/READING.md`, `mdm-engineering/references/storage-adapters.md` still describe legacy callers and a cutover
  - [ ] `CONTEXT.md`: entries that describe the DuckDB silver, ledger epochs and a cutover
- [ ] The seven wastes: each remaining repeated check, wait or hand-off named and removed, with the function kept shown by the tests
- [ ] Skills and guides rewritten to the simple path: onboarding a source is assembling its files and running `rules check`
- [ ] Learning → skill
