# Retire PostgreSQL business routines and caller paths

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 07

## Question

Can the active PostgreSQL business implementation be removed after the shared caller is qualified?

## Parts

- [ ] Add a new owner migration retiring the inventoried superseded business routines; preserve historical migration files and required storage enforcement.
- [ ] Delete superseded active Python SQL caller paths, policy branches and duplicated database calculation tests; retain transactions, uniqueness, grants, migrations, concurrency, authority and recovery integration checks.
- [ ] Verify a populated PostgreSQL upgrade preserves durable state and the normal caller no longer invokes retired routines; repeat normal MySQL parity and unchanged replay.
- [ ] Publish before/after active-code and routine counts separately from historical SQL; do not count retained historical migrations as unfinished active business logic.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

No normal caller reaches retired PostgreSQL business routines; both workflows still pass and the database retains authoritative atomic enforcement.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
