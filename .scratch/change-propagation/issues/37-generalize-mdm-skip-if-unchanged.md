# 37 — Generalize the domain-content-hash skip-if-unchanged path to every MDM entity type

**What to build:** Give adviser, person, security, fund, and audit-firm
resolution the same skip-if-unchanged fast path `run_companies` already
has, using the already-generic `MdmSourceRef.source_content_hash` column.

**Blocked by:** None — the schema is already generic; the decision to
generalize is already made (Ticket 06).

**Status:** ready-for-agent

- [ ] Confirm, per entity type, whether its resolver already reads/writes
  `source_content_hash` to skip unchanged rows — this was not fully audited
  while resolving Ticket 06, only confirmed true for `run_companies`.
- [ ] For every entity type found not to have it, wire the same
  skip-if-unchanged check its resolver already has for match/survivorship,
  keyed on `source_content_hash` comparison against the stored value from
  the prior resolution.
- [ ] A test per entity type proves an unchanged source row is skipped
  (no new `MdmChangeLog` row, no re-resolution work) while a changed row
  still resolves normally.

## Notes

Surfaced while resolving [06 — Decide MDM affected-key closure and
publication outbox](06-decide-mdm-closure-and-outbox.md) — see that
ticket's Answer. `source_content_hash` lives on the entity-type-generic
`MdmSourceRef` table (keyed to `mdm_entity`, not to any one entity type),
so this is wiring per resolver, not a schema change.
