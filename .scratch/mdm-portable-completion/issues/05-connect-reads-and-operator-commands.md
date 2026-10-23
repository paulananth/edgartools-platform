# Connect master reads and operator commands

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 04

## Question

Can installed consumers and operators use normal engine-selected MDM read and inspection paths?

## Parts

- [ ] Finish current/history/detail/relationship/context reads and real master-identifier lookup used by Silver.
- [ ] Connect counts, connectivity, health, inspection and supported publication commands to selected-engine storage; preserve authorization and bounded exact-key plans.
- [ ] Verify original JSON, large numbers, Unicode and opaque identifiers survive transport; keep errors and public evidence free of source values.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal installed reads and commands work on both engines, including the real Silver-facing lookup; helper callbacks alone do not qualify the path.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
