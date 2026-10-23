# Inventory the current caller and preserve unfinished work

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: none

## Question

Which existing paths must be replaced, retained as storage guarantees, or preserved as historical migrations?

## Parts

- [ ] Inventory normal migration, Merge Stage, configuration registration, scope, matching, correction, assessment, history, details, publication, workers and health commands; name their live callers and PostgreSQL-only dependencies.
- [ ] Account for every active PostgreSQL routine by responsibility and caller; distinguish business computation from atomic storage enforcement and immutable historical SQL. Record measured line counts without a deletion target.
- [ ] Review and allocate the uncommitted candidate-index, RecordReader and destination-authority work from codex/mdm-completion-20261023. Preserve its originals; do not carry unrelated work or silently stage another session’s changes.
- [ ] Record a case matrix for existing outcomes, configured vocabulary, rollback, concurrency, stale work and replay; distinguish existing evidence from unqualified integration.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Source inspection and a caller/routine inventory identify every remaining PostgreSQL business entry point and the ticket replacing it; no provider or production access.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
