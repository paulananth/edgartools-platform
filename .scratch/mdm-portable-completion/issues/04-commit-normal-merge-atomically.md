# Commit the normal Merge Stage atomically

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 02, 03

## Question

Can one shared normal MDM caller prepare and atomically commit every merge effect on either storage engine?

## Parts

- [ ] Connect shared identity replay, value selection, relationships and detail preparation to the normal Merge Stage save path.
- [ ] Commit source assertions, decisions, identities, current masters, history, detail lists, generation/checkpoints and publication as one admitted destination transaction.
- [ ] Validate observed state and registered pins at the destination; refuse stale assessments and competing writers; preserve batch/root-run association and duplicate semantics.
- [ ] Prove history boundaries, identity uniqueness, corrections, retirement and unchanged replay with invented configuration.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal merges on both real engines have equivalent durable outcomes; injected failures leave no partial master, history, checkpoint or publication changes.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
