# 01: Reset the hosted stores, gate them READY and reload

Status: open
Type: task
Owner: claude (operator, 2026-11-25: "codex is not owning this you own it")

Operator, 2026-11-25: "this is a new request"; "fix skills and scripts if anything is unclear or wrong". Scope: clear the hosted data and control tables, preserve the databases and schemas, and keep the config database.

## How several agents work on it

Claude owns and runs this ticket; other agents take a part only when Claude hands it over, and no agent edits a part Claude has claimed.

- **Claim a part** by writing `Claimed by: <runtime>/<branch>, <ET time from the clock>` under it before any work. A part with a claim is not taken by another agent.
- **One branch per agent**, cut off `origin/main` in its own worktree (`claude/`, `codex/`, `grok/`); no agent edits another's branch or this file's claimed parts. An agent adds its own ticks and nothing else, and rebases on conflict (keep both sides).
- **Order**: part A first (it decides what is reset), B to D can run in parallel after A, E needs B to D, F needs E, G at the end.
- **Live steps need the operator's words** (stop, restore or replace shared data): record them with the exact words and ET time; never run one on a store another agent is using (see CLAUDE.md, Shared local data).
- Never print a secret, a password, a token or a database address; counts only.
- The reset runs from the CI-built loader image through the pipeline, never from a checkout.

## Checklist

### A. Scope and drain (first)
- Claimed by: claude/hosted-clearout-20261125, 2026-11-25 13:31 ET
- [x] Clarify that an empty `load_jobs.py --status` does not prove Bookkeeping has no open runs or leases; HOSTED-LOADS now requires independent run and lease checks (`git diff --check`), 2026-11-24 18:49 ET
- [x] Add a generic table-level reset tool and hosted-load skill procedure; it accepts only explicit per-store `DROP`/`TRUNCATE` manifests and never drops databases (`py_compile`, CLI help and `git diff --check`), 2026-11-24 21:35 ET
- [x] Prepare and review explicit full-inventory `TRUNCATE` manifests, each with `--require-all-tables`; apply only the plan digest reviewed for that store. Data/control databases and schemas stay in place; the config database is excluded (live reset receipts in the private stores folder) (2026-11-25 13:31 ET)
- [x] Scope: reset all resettable tables in MDM (13), RDM (10), Silver (21), Bookkeeping (5) and Change Journal (1), to clear the hosted data/control stores for a fresh run. Restore published RDM sets from Git before readiness/mirroring: 11 code sets, 11 versions, 7,272 published codes; all 11 pins ok. Keep `mdm.migration` (1 row), `silver.table_spec` (21 rows) and all Rules tables in config (`policy` 2, `dataset_reading` 21, `rules_used` 21, `draft` 0). The mirror target is absent; its record remains configured for RDM's published codes when mirroring is set up after the load. Operator: "Clearing the hosted Snowflake Postgres" and "keeps the config database" (2026-11-25 13:31 ET)
- Reset tables: `mdm.mastering_decision`, `mastering_deferred`, `mastering_delivery`, `mastering_file`, `mastering_identifier`, `mastering_lookup`, `mastering_lookup_progress`, `mastering_master`, `mastering_name_key`, `mastering_profile`, `mastering_record`, `mastering_review`, `mastering_withheld`; `rdm.code`, `code_label`, `code_path`, `code_set`, `code_set_hint`, `code_set_usage`, `code_set_version`, `crosswalk_row`, `level`, `published_code`; `silver.adv_custody`, `company_fact`, `company_line_item`, `company_line_item_input`, `company_measure`, `company_measure_input`, `insider_position`, `insider_reporting_owner`, `ipo_filing`, `master_binding`, `nport_holding`, `prospectus_cover_line`, `prospectus_offering`, `prospectus_underwriter`, `registration_offering`, `registration_statement_line`, `relationship`, `relationship_evidence`, `relationship_path`, `thirteenf_filing`, `thirteenf_holding`; `bookkeeping.checkpoint`, `journal_outbox`, `lease`, `pipeline_run`, `work_item`; `journal.event`. Every action was `TRUNCATE`.
- [x] Drain: no load process (worker had only activity worker/exporter), no open Bookkeeping runs (538 complete; 0 leases/work items), no application client sessions or WAL senders/replication slots; two idle Snowflake-managed extension workers had no state or transaction and were permitted by the reset script (2026-11-25 13:31 ET)
- [x] Kept-store counts read before and after: `mdm.migration` 1, `silver.table_spec` 21, config Rules 2 policies/21 readings/21 used/0 drafts; verified unchanged after reset (2026-11-25 13:31 ET)

### B. Init steps 1a to 9, by store (parallel after A, one agent each)
- [ ] B1 MDM and RDM: init in order, read back the schema version and the code-set counts
- [ ] B2 Rules and Bookkeeping: init in order, read back the rule versions and the control tables
- [ ] B3 Change Journal and Silver: init in order, read back the journal and the silver login's grants (no `TEMPORARY`, no DDL at run time)

### C. Roles and access (parallel after A)
- [ ] Harden the hosted roles (`harden-hosted-roles.py`): every login role holds its connection limit; the audit's POL and access controls pass

### D. Catalog (parallel after A)
- [ ] The catalog holds the reset stores' current rules (`rules catalog publish`, then `check` returns `confirmed`); no history carried over unless the catalog-status ticket says so

### E. Gate (needs B to D)
- [ ] `readiness.py` full pass: READY on every check, and the engine build (`--build-engine`) passes

### F. Reload (needs E)
- [ ] Load from the CI-built loader image through the pipeline, a default load first, then a forced load only on the operator's words; every step done or its failure reported with its cause
- [ ] Finish (links, master ids, mirror readback) ends within five minutes on this store, or the time is reported and a ticket opened

### G. Close
- [ ] Counts match the pre-reset record for what was kept, and the new stores' counts are reported (counts only, no data values)
- [ ] Learning → skill: name the skill line changed (`data-operations/HOSTED-LOADS.md` or `data-platform/HOSTED-MIRRORING.md`), or write "none"

## Configuration follow-up

- [ ] Move MDM migration records and Silver table specifications into the configuration managed by deployment. Preserve `mdm.migration` and `silver.table_spec` during every data clear until the replacement is deployed and verified. Keep installed schema evidence tied to the deployment that produced it.

## Comments

2026-11-24: Read-only preflight found two client sessions and two idle extension workers on the data database. `load_jobs.py --status` found no active steps (43 of 43 done), while Bookkeeping reported 59 runs in `running`, zero in `waiting` and zero in `blocked`. One sampled run had expected_count 0, no work items and no lease; all-run lease inspection was still running after about 60 seconds and was stopped without a total. These open runs and client sessions remain unresolved.

2026-11-24: Operator clarified that this work preserves the hosted databases and uses explicit table-level drop/truncate actions. Live mirror readback found one configured mirror and 24 tables in `REPLICATING`. No table reset, PostgreSQL restart or reload has been performed.

2026-11-25 13:31 ET As owner, applied full-inventory `TRUNCATE` plans on the data/control stores. Read-back: MDM, Silver, Bookkeeping and Change Journal resettable rows are zero; RDM restored from published Git pins (11 sets/11 versions/7,272 published codes, every pin ok); `mdm.migration` 1 and `silver.table_spec` 21 remain; config Rules counts unchanged (2 policies, 21 readings, 21 used, 0 drafts). The data database has no publications, replication slots or WAL senders; the mirror procedure reported the configured mirror absent and its target database was absent. Initialization, readiness and reload were outside this clear-out request and remain open on the reset ticket.
