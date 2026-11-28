# Gold links: by identifier, several kinds, Set Aside out of scope

Status: open
Type: task
Owner: claude (map decisions 7, 9, 10)
Blocked by: 02, 04

A link resolves by its identifier on any master of its kinds; a link may name several kinds; its test counts only rows whose
key the Set Aside table does not hold, and every one resolves to exactly one master. The reporting owner's two links become one,
`[person, company]` by CIK.

## Checklist

- [ ] GoF consult on `edgar_warehouse/gold/views.py`
- [ ] Silver specs: `kinds` lists where an issuer or owner may be either
- [ ] Views and tests generated; a test per kind of link fails on today's generator
- [ ] `/code-review`
- [ ] Learning → skill
