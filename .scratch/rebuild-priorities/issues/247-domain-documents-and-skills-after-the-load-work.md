# 247: Domain documents and skills say what the load work learned

Type: task. Status: resolved (operator, 2026-11-16: "Update domain documents and skills"). Blocked by: none.

## Parts

- [x] 2026-11-16 09:25 ET `CONTEXT.md`, Merge Stage: merges of one entity type run side by side when they only join stored master records; one that creates or merges them runs alone (the built behaviour, PR 1831).
- [x] 2026-11-16 09:25 ET `data-operations` RUNBOOK, "File and rule changes": how to prove an unchanged rerun (count every table before and after, own log folder, no `--finish`, read a difference by what wrote it, what counts cannot show).
- [x] 2026-11-16 09:25 ET `change-journal` SKILL, "Skipping and forcing": a file's identity holds its target; a target with no record step is never skipped.
- [x] Already in `main` or PR 1832: `--workers` at either grain and the kind lock (data-operations RUNBOOK, mdm-engineering, bookkeeping SKILL); `record: false` (bookkeeping SKILL, PR 1832); the test-writing rules (`docs/agents/watching-and-testing.md`).
- [x] Verified: genericity, no-ticket-number, guide-path and load-chain tests (142 passed); `data-operations/SKILL.md` stays under 500 lines (487).
- [x] Learning → skill: this ticket is the learning; the three lines above.
