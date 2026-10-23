# Connect indexed records to shared matching and scope

Type: task
Status: open
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 01

## Question

Can the normal Merge Stage obtain all affected records through exact indexed portable reads?

## Parts

- [ ] Finish shared indexed scope, matching, correction, held-value and membership reads; validate immutable references, provenance and current-record freshness.
- [ ] Derive identifier namespaces, census/cascade paths and comparison selectors solely from pinned configuration; validate changed routes against retained latest readings.
- [ ] Prove invented sources, kinds, fields and namespaces, both arrival orders, corrections and unchanged replay; inspect actual bounded per-key plans beside populated unrelated records.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal scope and matching return equivalent intended records on both engines without whole-table scans, hardcoded policy or a second merge algorithm.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.
