# 01: Reset the hosted stores, gate them READY and reload

Status: open
Type: task
Owner: codex (operator, 2026-11-24 17:24 ET: "This is for codex")

Operator, 2026-11-24 17:21 ET: "Create the reset ticket multiple agents will be working on completing it, so create pr". The reset is the hosted-store reset the platform runs after a schema or rule change that old stores cannot take (the last one: ticket 14 of `hosted-mirroring`, #2056). The operator did not name another reset; if a different reset was meant, say so on this ticket before any part is claimed.

## How several agents work on it

Codex owns and runs this ticket; other agents take a part only when Codex hands it over, and Claude does not edit a part Codex has claimed.

- **Claim a part** by writing `Claimed by: <runtime>/<branch>, <ET time from the clock>` under it before any work. A part with a claim is not taken by another agent.
- **One branch per agent**, cut off `origin/main` in its own worktree (`claude/`, `codex/`, `grok/`); no agent edits another's branch or this file's claimed parts. An agent adds its own ticks and nothing else, and rebases on conflict (keep both sides).
- **Order**: part A first (it decides what is reset), B to D can run in parallel after A, E needs B to D, F needs E, G at the end.
- **Live steps need the operator's words** (stop, restore or replace shared data): record them with the exact words and ET time; never run one on a store another agent is using (see CLAUDE.md, Shared local data).
- Never print a secret, a password, a token or a database address; counts only.
- The reset runs from the CI-built loader image through the pipeline, never from a checkout.

## Checklist

### A. Scope and drain (first)
- Claimed by: codex/codex-hosted-reset-load-20261124, 2026-11-24 18:40 ET
- [x] Clarify that an empty `load_jobs.py --status` does not prove Bookkeeping has no open runs or leases; HOSTED-LOADS now requires independent run and lease checks (`git diff --check`), 2026-11-24 18:49 ET
- [x] Add a generic table-level reset tool and hosted-load skill procedure; it accepts only explicit per-store `DROP`/`TRUNCATE` manifests and never drops databases (`py_compile`, CLI help and `git diff --check`), 2026-11-24 21:35 ET
- [ ] Prepare and review the exact per-store table manifests and actions before applying them
- [ ] Name the exact tables and why each is reset (the schema or rule change), the stores in scope (MDM, RDM, Rules, Bookkeeping, Change Journal, Silver) and the stores kept; preserve databases and schemas
- [ ] Drain: no load, no extension worker and no other agent's session on the hosted Postgres (HOSTED-LOADS.md, "drain before reset"); say who was using it
- [ ] Back up what is kept (counts before: rows per kept store)

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

## Comments

2026-11-24: Read-only preflight found two client sessions and two idle extension workers on the data database. `load_jobs.py --status` found no active steps (43 of 43 done), while Bookkeeping reported 59 runs in `running`, zero in `waiting` and zero in `blocked`. One sampled run had expected_count 0, no work items and no lease; all-run lease inspection was still running after about 60 seconds and was stopped without a total. These open runs and client sessions remain unresolved.

2026-11-24: Operator clarified that this work preserves the hosted databases and uses explicit table-level drop/truncate actions. Live mirror readback found one configured mirror and 24 tables in `REPLICATING`. No table reset, PostgreSQL restart or reload has been performed.
