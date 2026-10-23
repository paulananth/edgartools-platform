# Install governed MDM storage on both engines

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-23 14:39 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 01

## Question

Can the normal owner migration install and upgrade the same governed storage contract on PostgreSQL and MySQL?

## Parts

- [ ] Connect the existing portable adapter to the normal MDM owner migration; retain immutable policies, dataset contracts, configured kind authority, version pins and runtime restrictions.
- [ ] Preserve migration checksums and retained records; qualify populated upgrade, interruption, already-open runtime connections and repeat migration.
- [ ] Refuse missing or changed configuration, direct runtime governance writes and excess privileges; retain owner/runtime separation.
- [ ] Qualify exact registry JSON values and reject an untracked or structurally changed registry; preserve all existing prepared-effect protocol fingerprints.
- [ ] Qualify the normal migration CLI and independently installed packaging for the new storage helper.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal migration commands install and upgrade both real engines with restricted runtime roles; populated state and pinned configuration survive unchanged.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.


## Initial design consult

The existing registry API already provides shared policy/dataset registration
and typed reads. Its tests create their own tables, so they do not implement
normal owner migration. Reuse that API and the skill-owned prepared-effect
adapter; keep the PostgreSQL native save path intact until its replacement is
qualified. Add the missing owner installation and validation behind the existing
normal migration command. No second matching or policy algorithm.

MySQL DDL must resume under an owner lock with a checksummed pending marker,
runtime writes/execute fenced during installation, structural and grant readback,
and append-only registry protection. Configured vocabulary arrives from the
pinned catalog as data. Normal MySQL Merge Stage support remains a later ticket;
this ticket qualifies its governed storage installation and registration path.

GoF: current history (#1073, #1096, #1121, #1148) supports extending the existing
adapter seam. A new class hierarchy would not close the owner migration or
atomic-authority gaps and would increase migration/review cost.

## Implementation review — 2026-10-23 15:13 ET

### Standards

Dedicated Codex worktree; overlap guard passes. Historical migrations are
unchanged. Evidence uses invented fixtures and counts only. Registry tables,
grants, checksums and recovery live in the skill-owned adapter; catalog kinds
and policy contents arrive as data.

### Spec

Normal MySQL owner migration now installs the governed registry and retained
prepared-effect storage. Runtime governance writes and prepared-effect EXECUTE
remain denied. PostgreSQL keeps its existing normal save path and gains registry
structure and inherited column-write checks. Normal MySQL Merge Stage and SQL
Server integration remain later tickets. Initial regression evidence: 110
PostgreSQL and 118 MySQL adapter checks pass; independent installation and the
additional concurrent reader/migration case remain under qualification.

### GoF

The diff extends the established Adapter boundary rather than introducing a
second merge implementation or class hierarchy. New owner-installation logic
is isolated from application policy. The cost is a new versioned registry DDL
contract to retain; checksummed installation and corruption/recovery tests
make that cost explicit. No further pattern refactor is justified by the
current history or this diff.
