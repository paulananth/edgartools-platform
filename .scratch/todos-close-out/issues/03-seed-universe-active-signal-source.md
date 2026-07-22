# 03 — Seed universe: what signal determines a company is no longer active?

Type: grilling
Status: open
Blocked by: (none)

## Question

TODOS.md's seed-universe entry requires demoting companies that are no
longer active so they stop generating candidate work, but doesn't decide
the signal source. Candidates: SEC's own company-status data (if any,
via submissions.json), a delisting feed, or an existing internal
`tracking_status` transition already used elsewhere in this pipeline.
Decide the source and how it plugs into `run_seed_universe_command` /
`sec_company_sync_state`.

## Answer

(resolved on close)
