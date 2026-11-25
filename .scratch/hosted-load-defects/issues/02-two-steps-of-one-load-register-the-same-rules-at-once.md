# 02: Two steps that start together register the same merge policy at once, and one fails

Status: open
Type: bug
Blocked by: none

Found 2026-11-25 at the start of the hosted reload (2026-11-24 22:20 ET): the first two steps (company and person) started
in the same second. Each ran `rules register --source`, which inserts the merge policy under its digest; the second insert
hit the primary key of `rules.policy` (`UniqueViolation`, `policy_pkey`) and the step stopped (`rc=1`). Its second attempt
started at once and passed. Nothing was lost, but the first attempt of a load's first step fails whenever two steps
register the same policy together.

## Checklist

- [ ] Test first: two registrations of the same policy digest at once both succeed and leave one row
- [ ] Register with an insert that does nothing when the digest exists (`on conflict do nothing`), so the second caller reads
      the row the first wrote
- [ ] Learning → skill: none expected; name the line if one changes
