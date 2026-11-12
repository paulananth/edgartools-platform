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
  - [ ] `skills/data-operations/SKILL.md` still names `workers verify` and one verifier a run (four passages): Codex's open PR 1714 changes that file, so the edit waits for it to merge (overlap guard)
  - [ ] Left for the skills and words parts: "verifier" in prose of `skills/data-platform/READING.md`, `COMBINING.md`, `skills/data-operations/RUNBOOK.md`, `skills/mdm-engineering`, and in the "verifier byte budget" error texts
- [ ] Schema files: one current schema file per store; `init` creates it; the upgrade command kept
  - [x] (2026-11-12 15:10 ET) Bookkeeping: `migrations/schema.sql` replaces ten numbered files (and `mysql-v1.sql` is edited in place). A store built from it dumps the same as one built from the ten files plus the run-checks change (`pg_dump -s`, compared; the only difference is the grants on the new function). `migrate` applies it, then any numbered file added later; a store on the earlier files is refused with "rebuild the store"
  - [ ] MDM (30 files), RDM (9), Change Journal (3), silver writer (2)
- [ ] Words: no reference to a migration from an older system, a legacy path, a cutover or a retired stage in the code, rules, guides, documents and skills
- [ ] The seven wastes: each remaining repeated check, wait or hand-off named and removed, with the function kept shown by the tests
- [ ] Skills and guides rewritten to the simple path: onboarding a source is assembling its files and running `rules check`
- [ ] Learning → skill
