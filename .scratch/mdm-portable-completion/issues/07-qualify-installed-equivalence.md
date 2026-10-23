# Qualify the installed MDM workflow on both engines

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 05, 06

## Question

Does the independently installed normal workflow prove equivalent complete behavior on PostgreSQL and MySQL?

## Parts

- [ ] Install the committed bundle outside the checkout and run the normal migration, configured worker, Merge Stage, context, master lookup and publication paths on each real engine.
- [ ] Cover invented vocabulary, identity uniqueness, held-back records, relationships, history/details, concurrency, stale work, interruption, recovery, populated upgrades and unchanged replay.
- [ ] Record counts and outcomes tied to the tested revision; run affected tests only, below the local five-minute cap per run; retain SQL Server adapter checks without claiming full qualification.
- [ ] Review Standards, Spec and GoF and resolve material findings; ensure the tested code is the installed code.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Both independently installed normal callers pass the full case matrix. Adapter-only checks and PostgreSQL-only proofs cannot close this gate.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
