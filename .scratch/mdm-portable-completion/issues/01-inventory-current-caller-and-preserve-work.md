# Inventory the current caller and preserve unfinished work

Type: task
Status: resolved
Assignee: Codex
Claimed: 2026-10-23 13:13 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: none

## Question

Which existing paths must be replaced, retained as storage guarantees, or preserved as historical migrations?

## Parts

- [x] Inventory normal migration, Merge Stage, configuration registration, scope, matching, correction, assessment, history, details, publication, workers and health commands; name their live callers and PostgreSQL-only dependencies. — eight normal operation rows and all native entry points inventoried; 2026-10-23 13:20 ET.
- [x] Account for every active PostgreSQL routine by responsibility and caller; distinguish business computation from atomic storage enforcement and immutable historical SQL. Record measured line counts without a deletion target. — 36 installed functions classified; 27 files / 4,874 historical SQL lines; fresh PG16 catalog matches; 2026-10-23 13:20 ET.
- [x] Review and allocate the uncommitted candidate-index, RecordReader and destination-authority work from codex/mdm-completion-20261023. Preserve its originals; do not carry unrelated work or silently stage another session’s changes. — PR #1148 merged, exact qualified tree match, private patch reverse-check and new-test hash match; 2026-10-23 13:20 ET.
- [x] Record a case matrix for existing outcomes, configured vocabulary, rollback, concurrency, stale work and replay; distinguish existing evidence from unqualified integration. — eleven-row behavior matrix separates existing evidence from remaining normal-caller qualification; 2026-10-23 13:20 ET.
- [x] Learning → skill: update its owning skill on a separate branch/PR, or record none. — none; existing engineering boundaries applied; reusable authority guidance is tracked separately in PR #1150; 2026-10-23 13:20 ET.

## Acceptance evidence

Source inspection and a caller/routine inventory identify every remaining PostgreSQL business entry point and the ticket replacing it; no provider or production access.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

Claimed after PR #1148 merged as 4b1bb68f, as the operator requested.


## Answer

[Caller and routine inventory](../assets/caller-inventory.md) accounts for all
36 functions installed by current normal PostgreSQL migration, every remaining
normal-caller operation, the preserved work allocation and the required behavior
matrix. [Routine source manifest](../assets/routine-inventory.json) records the
latest source locations, responsibility groups and internal routine references.

There are 4,874 historical migration lines, but 1,130 latest installed function
source lines; neither is a deletion budget. Mixed write routines must be split
without losing atomic storage enforcement. Historical migrations remain intact.
The normal MySQL caller is still unsupported. No runtime code changes here.

The next frontier is governed storage and indexed record reads. Full installed
workflow qualification gates the later PostgreSQL routine retirement.
