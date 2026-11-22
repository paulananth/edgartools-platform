# 14: Finish hosted mirroring: the parts tickets 04 and 13 left open

Status: open
Type: task

The operator closed tickets 04 and 13 on 2026-11-21 ("close all ticket on this map"). Their parts that were not done moved here, unchanged in meaning.
Parts marked "approval" or "words" wait for the operator's own words before they run.

## Checklist

- [ ] Access by schema in a shared database: reset, hardening (the mirror login's CONNECT), readiness, catalog readers, local test stores
- [ ] `rules/exposure.yaml` and `rules/gold/gold.yaml`: one target database, mdm's source schema `mdm`
- [ ] Prove on the local test server with the two-database layout: init, a small load, links and master ids, the catalog reader
- [ ] Readiness: `discovery_reader` (the catalog reader) holds a connection limit (audit CST); the role guards hold it, apply after merge, then the gate
- [x] Mastering moved from `public` into schema `mdm`, with audit objective SCH: PR #1997 2026-11-21 09:27 ET
- [ ] Hosted: the live stores hold the mastering tables in `public` until the next init; a reset (init steps 1-9) creates them in `mdm`, the audit's SCH control passes, and the one mirror is created with `MDM` as the schema
- [ ] Follow-up (no-DDL rule): the silver writer still stages each delivery in a temporary table, so the databases keep TEMPORARY
- [ ] Finish under five minutes on this store: rebase `claude/links-reads-one-pass`, merge, rerun `--finish`
- [ ] The snapshot cost of the one mirror read from metering history against the bounds (5 credits for a mirror)
- [ ] Hosted: rename the two kept databases (drop the `DB_` prefix) and drop the two old targets (waits for the operator's ANANP11 words); a one-line change per name in `rules/snowflake.yaml`
- [x] The orphan targets `DB_EDGARTOOLS_MIRROR_MDM` and `DB_EDGARTOOLS_MIRROR_SILVER`: dropped (operator, 2026-11-22: "dropped targets ... check and update"); verified `SHOW DATABASES LIKE '%EDGARTOOLS%'` as the auditor role lists only `EDGARTOOLS_GOLD` and `EDGARTOOLS_GOVERNANCE` 2026-11-22 12:08 ET (the auditor sees only databases its role can see)
- [ ] Owner role and ownership grants in the access Terraform root (the next access apply imports the role and the two grants first)
- [ ] Hosted RDM still holds the six old code-set versions: its own command or ticket (ticket 07's deferred part)
- [ ] Follow-up ticket: master ids and links as joins inside the data database
- [ ] Credential policies: the next access plan creates the schema and both policies in the Gold database, re-attaches them to the account and drops `EDGARTOOLS_GOVERNANCE` (a destroy: needs `--allow-destroy` and the operator's own approval)
- [ ] Re-run the audit on `snowflake`: POL passes once the policies sit in the Gold database and equal the file
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
