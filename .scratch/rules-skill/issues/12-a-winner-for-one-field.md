# A winner for one field: the Mapping Document and the skill say it right

Type: build
Status: resolved: merged in #744 (2026-10-02 audit, mastering to-do 01).
Was: in progress

## Outcome

Operator, 2026-09-28, asking why one field's winner "can't be set on its
own" (a claim in PR #743): "Why and explain", then "Fresh branch".

The claim was wrong. The merge engine already takes a rule per field:
`kinds.<kind>.fields.<name>` inherits the kind's `defaults` and may change
any part of it, its source order included
(`edgar_warehouse/mdm/clean/survivorship.py` `_select_values`: "A declared
field inherits the default and may override any part of it, such as its own
source order"). `fields` is an authority-bearing section
(`AUTHORITY_SECTIONS`), and `check_policy` accepts a Company kind with a
per-field `address` rule (checked on main 089c588c, 2026-09-28).
Only `company.yaml` has none today, so the Mapping Document showed the
default order alone, and the Rules skill told Claude to log a per-field
change as a ticket.

## Checklist (times ET)

- [x] Branch off main 089c588c (17:45 ET).
- [x] `/gof-refactor-reviewer` (2026-09-28): leave the structure. `mapdoc.py`
  has one commit; the change is inside `_field_sources` and the two "Who
  wins" sheets, reading the same rule `_select_values` builds
  (`{**defaults, **fields[name]}`). No repeated change to fold.
- [x] "Who wins" (source and kind workbooks) shows each field's own rule
  when it has one: its order, marked "Its own rule" (with any other setting
  it changes), and its rules path; other fields say "Kind default".
- [x] The skill: a changed winner for one field is `fields.<name>.sources`
  in the kind file; the steward who made it approves. REFERENCE.md names
  what a field's own rule may change.
- [x] A test: a per-field rule shows in the workbook, and `diff` reports a
  steward's change to it (`test_rules_mapdoc.py`, 14 passed).
- [x] Three-axis review (2026-09-28): no bugs. Fixed: a field rule with no
  order of its own says its order is the kind default; the skill says a
  source left out of a field's order is ignored for that field, and that
  a source not in the kind's ranks needs the operator's ruling.
- [ ] PR #744, CI; merge on the operator's word.
