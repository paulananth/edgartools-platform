# The runbook creates the mirror, for only the exposed subset, after the load

Status: resolved
Type: task

Operator, 2026-11-18, while the stores were reset and loaded again: "You also need to create mirror only for subset of tables must
update skills and runbook".

## Findings

- The repository already holds the subset: `rules/exposure.yaml` selects 18 final tables (16 silver, 2 MDM) with the operator's
  approval words, and its target database is marked "not built yet". The hosted mirroring guide already says explicit tables, never a
  schema, and a separate approval before `CREATE_MIRROR`.
- Nothing said when to create the mirror, from what, or what a store reset does to one; the init runbook had no mirror step.
- A mirror reads one source database and the stores are separate databases: the create plan has to name each mirror's source
  database (the guide's source-consolidation gate), not assume a shared one.

## Parts

- [x] The guide says the mirror is created once, after the first load, from the exposure list only, with the four steps and the reset
  rule (2026-11-18 12:07 ET; read in the PR)
- [x] The init runbook has the "Mirror the final tables" step with its done condition and the reset warning (2026-11-18 12:07 ET; read in the PR)
- [x] The guide and the runbook say creation waits for the source-consolidation gate: one mirror reads one source database and the six
  stores are separate (2026-11-18 12:09 ET; a review found the step could not be built on this layout as first written)
- [ ] ~~Create the mirror~~ deferred to ticket 01 (`01-managed-mirror-guidance`, where creation stays unapproved): it needs the finished load, the read-only pre-flight and the
  operator's approval of the create plan (source database per mirror, tables, refresh, cost); `rules/exposure.yaml` says it is not built
- [x] Learning → skill: data-platform HOSTED-MIRRORING.md, "After the first load: mirror only the exposed subset" (2026-11-18 12:07 ET; this ticket)
