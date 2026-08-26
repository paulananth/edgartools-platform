# 42 — Fund bulk resolution's pfid-keyed dedup starves MDM export of change signal

**What to build:** Re-key `resolve_funds_bulk`'s existing-row dedup so a
later accession amending an already-known private fund still produces an
`MdmChangeLog` row, sized against the real one-time re-stage cost of
switching the key on the live fund population.

**Blocked by:** None

**Status:** ready-for-agent

- [ ] Decide the re-keying approach: switch `resolve_funds_bulk`'s dedup
  key (currently `private_fund_id` when present, else
  `accession_number:fund_index`) to always be `accession_number:fund_index`
  — matching `resolve_advisers_bulk`'s existing per-accession key — while
  keeping `private_fund_id`-based lookup (`by_pfid`) for entity *identity*
  matching unchanged. Confirm no other consumer reads fund
  `MdmSourceRef.source_id` expecting pfid shape (checked once already, see
  Notes — re-verify before shipping).
- [ ] Size the one-time backlog cost: on the first run after the key
  changes, every already-seen pfid-keyed fund's most recent accession will
  no longer match `existing_sources` and will re-stage/re-log — bound how
  many `MdmEntityAttributeStage`/`MdmChangeLog`/`MdmSourceRef` rows that
  produces against the live fund population before shipping (production has
  seen `fund_index` past 22,000 for a single adviser — see CLAUDE.md's
  schema-conventions note — so the total fund population is not small).
- [ ] Fix + regression test proving: (a) an amendment to an already-known
  pfid now produces a new `MdmChangeLog` row (the inverse of the
  characterization test this ticket obsoletes,
  `tests/mdm/test_adv_bulk_resolution.py::test_fund_bulk_resolution_dedups_by_private_fund_id_not_accession`
  — update or replace it once fixed); (b) a genuinely unchanged accession
  (identical re-run) still doesn't duplicate rows, preserving the
  restart-idempotency `test_adv_bulk_projection_is_latest_and_idempotent`'s
  sibling test already proves for funds.

## Notes

Found while resolving [37 — Generalize the domain-content-hash
skip-if-unchanged path to every MDM entity type](37-generalize-mdm-skip-if-unchanged.md):
writing that ticket's required "a changed row still resolves normally" test
per entity type caught that fund's dedup is keyed on `private_fund_id`, not
`accession_number` (unlike adviser, which is always accession-keyed). A
fund's golden `MdmFund` record *does* still refresh on a later accession
(the `setattr` loop in `resolve_funds_bulk` runs unconditionally, outside
the dedup check) — but no new `MdmChangeLog` row is written, and
`MDMExporter.export_pending` (`edgar_warehouse/mdm/export.py`) selects
pending work via `MdmChangeLog.exported_at IS NULL`. So a fund whose
`fund_name`/`aum_amount`/etc. change on a later ADV amendment silently never
gets re-exported to Snowflake gold, even though Postgres itself is correct
— a real freshness bug, not just a missing audit-trail row.

Deliberately **not fixed** as part of Ticket 37: this is a different bug
shape than that ticket's target (too-aggressive dedup dropping legitimate
change signal, the inverse of the unbounded-staging-growth bug Ticket 37
descends from — see that ticket's Answer for the precedent this follows,
`release-readiness` Ticket 100's identical "different bug shape, file
separately" call for the sibling `LIMIT`-without-`ORDER BY` plateau bug in
this same module). Also not a same-day fix because the re-stage backlog
cost on the live fund population is unsized — this ticket exists
specifically to size and then make that change deliberately, not as a
same-session line edit.

Already verified (re-verify before shipping, in case something new was
added in between): grepped every `MdmSourceRef` read in
`edgar_warehouse/mdm/*.py` — nothing reads fund-entity-type
`MdmSourceRef.source_id` expecting it to be pfid-shaped (the only other
`source_id`-keyed lookups are `adviser_by_accession`, scoped to
`entity_type="adviser"`). `MdmSourceRef`'s primary key is
`(entity_id, source_system, source_id)`, so multiple accession-keyed rows
per fund entity_id is exactly the shape adviser already uses safely — no PK
collision risk from switching the key.
