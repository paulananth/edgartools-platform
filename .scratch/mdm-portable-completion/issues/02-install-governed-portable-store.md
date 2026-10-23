# Install governed MDM storage on both engines

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 01

## Question

Can the normal owner migration install and upgrade the same governed storage contract on PostgreSQL and MySQL?

## Parts

- [ ] Connect the existing portable adapter to the normal MDM owner migration; retain immutable policies, dataset contracts, configured kind authority, version pins and runtime restrictions.
- [ ] Preserve migration checksums and retained records; qualify populated upgrade, interruption, already-open runtime connections and repeat migration.
- [ ] Refuse missing or changed configuration, direct runtime governance writes and excess privileges; retain owner/runtime separation.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal migration commands install and upgrade both real engines with restricted runtime roles; populated state and pinned configuration survive unchanged.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
