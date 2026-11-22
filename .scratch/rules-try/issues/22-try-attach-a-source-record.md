# Try Attach a source record

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/attach_record.py` only. The person pastes the policy, assertions, identities, and the bound list. The page calls `plan_record_matches`. Outcomes on the page: attach, create a master, send to review. The stored words `bind` and `mint` appear beside attach and create a master. Do not call `propose`. Do not open a database.

Invented pass: one invented identifier with one pasted master returns attach. The same identifier with two pasted masters returns send to review.

Known leftover: the same identifier-declaration import as ticket 16. This ticket does not add a database read.

## Checklist

- [ ] `attach_record.py` is the only file this ticket adds
- [ ] One pasted master returns attach
- [ ] Two pasted masters return send to review
- [ ] `propose` is not called and no database connection is opened
- [ ] Learning → skill

## Comments

