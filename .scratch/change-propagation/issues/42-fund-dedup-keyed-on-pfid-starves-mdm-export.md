# 42 — Fund bulk resolution's pfid-keyed dedup starves MDM export of change signal

**What to build:** Re-key `resolve_funds_bulk`'s existing-row dedup so a
later accession amending an already-known private fund still produces an
`MdmChangeLog` row, sized against the real one-time re-stage cost of
switching the key on the live fund population.

**Blocked by:** None

**Status:** resolved

- [x] Decide the re-keying approach: switch `resolve_funds_bulk`'s dedup
  key (currently `private_fund_id` when present, else
  `accession_number:fund_index`) to always be `accession_number:fund_index`
  — matching `resolve_advisers_bulk`'s existing per-accession key — while
  keeping `private_fund_id`-based lookup (`by_pfid`) for entity *identity*
  matching unchanged. Confirm no other consumer reads fund
  `MdmSourceRef.source_id` expecting pfid shape (checked once already, see
  Notes — re-verify before shipping).
- [x] Size the one-time backlog cost: on the first run after the key
  changes, every already-seen pfid-keyed fund's most recent accession will
  no longer match `existing_sources` and will re-stage/re-log — bound how
  many `MdmEntityAttributeStage`/`MdmChangeLog`/`MdmSourceRef` rows that
  produces against the live fund population before shipping (production has
  seen `fund_index` past 22,000 for a single adviser — see CLAUDE.md's
  schema-conventions note — so the total fund population is not small).
- [x] Fix + regression test proving: (a) an amendment to an already-known
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

## Answer

**Re-verified bullet 1 (no stale finding):** grepped every `MdmSourceRef`
read in `edgar_warehouse/mdm/*.py` again — still nothing reads fund-type
`MdmSourceRef.source_id` expecting pfid shape; the one other
`source_id == accession_number` lookup (`pipeline.py`'s
`_adviser_entity_id`) is explicitly scoped to `entity_type == "adviser"`.
Safe to switch the key.

**Sizing (bullet 2), queried live against prod MDM Postgres
(`edgartools-prod/mdm/postgres_dsn`, read-only session, connection string
never logged/printed):**

| Query | Result |
|---|---|
| `mdm_entity` rows where `entity_type = 'fund'` | 130,615 |
| `mdm_source_ref` rows for fund entities, `source_system = 'adv_filing'` | 130,615 (1:1 with entity count) |
| ...of those, pfid-shaped (no `:` in `source_id`) | 130,614 |
| ...of those, already accession-shaped (contains `:`) | 1 |
| `mdm_entity_attribute_stage` rows for fund entities | 653,075 (~5/fund, matching `FUND_FIELDS`' 5 members) |
| `mdm_change_log` rows for fund entities | 130,615 (1:1 with entity count) |

Every fund entity currently has exactly one `MdmSourceRef` row, and 130,614
of 130,615 are pfid-keyed. Since the key change is unconditional (no branch
left on whether pfid is present), **every one of those 130,614 funds' most
recent silver row will look "new" against the accession-keyed
`existing_sources` check on the very next `mdm run` after this ships** —
there is no way to make this incremental; it is a real, exactly-once
backlog by construction. Sized: ~130,614 new `MdmSourceRef` rows (~27
batches at the existing `_WRITE_BATCH_SIZE=5,000`), ~653,070 new
`MdmEntityAttributeStage` rows (~131 batches), ~130,614 new `MdmChangeLog`
rows (~27 batches) — roughly 185 additional batched `INSERT` statements
total in one `resolve_funds_bulk` call, each a single network round trip
under the existing `_execute_insert_chunks` machinery. This is the same
bulk-write path the module's own docstring says was built specifically to
handle "hundreds of thousands of historical rows" without one round trip
per row — the backlog is large but not a new scale for this code path, just
a bigger one-time write than a typical incremental run produces. Downstream,
`MDMExporter.export_all_pending` already loops `export_pending(batch_size=
500)` until exhausted, so the resulting ~130,614-row export backlog is also
absorbed by existing batching, just over more batches/wall-clock time than
usual — no redesign needed on the export side either.

**Decision: ship it.** The sizing came back bounded and within the code's
existing designed capacity on both the write and export sides — this isn't
the kind of open-ended "how bad could it get" question that needed a
user check-in before proceeding; it's a concretely bounded one-time cost
with a known shape. Implemented as a pure key-source change (see Notes
above): `resolve_funds_bulk`'s `source_ids` list comprehension in
`edgar_warehouse/mdm/adv_bulk.py` now always computes
`f"{accession_number}:{fund_index}"`, dropping the `private_fund_id`
preference entirely — `pfid` remains used only for `by_pfid`/entity-identity
matching (untouched).

**Regression tests** (`tests/mdm/test_adv_bulk_resolution.py`), tightened
after a `/code-review` pass on this diff (Standards axis flagged a
near-duplicate test, Spec axis flagged a missing `MdmSourceRef` assertion
against the ticket's own bullet 3(b) wording — both addressed below):
- `test_fund_bulk_resolution_a_new_accession_for_the_same_pfid_still_resolves`
  replaces the obsoleted characterization test — proves an amendment to an
  already-known pfid now produces a new `MdmSourceRef` row (under its own
  accession-based key) and a new `MdmChangeLog` row, and the golden record
  still refreshes correctly (bullet 3a).
- `test_fund_bulk_resolution_second_identical_run_does_not_duplicate_stage_or_change_rows`
  (added resolving Ticket 37) now also asserts `MdmSourceRef` counts, not
  just `MdmFund`/`MdmEntityAttributeStage`/`MdmChangeLog` — closing bullet
  3(b)'s literal requirement in full. A separate
  `test_fund_bulk_resolution_genuinely_unchanged_accession_still_dedups`
  was drafted and then folded into this one instead of kept alongside it:
  both exercised the same shape (rerun identical data twice, assert no new
  rows) against the same, already-current post-Ticket-42 key scheme, so a
  second near-duplicate test added no coverage this one didn't already give
  once strengthened.

`/code-review` found zero hard violations on either axis (Standards: no
CLAUDE.md conformance issues; Spec: all three bullets fully implemented,
no scope creep — `by_pfid`/`by_adviser_name`/entity-identity matching
verified byte-for-byte untouched).

Full `tests/mdm/test_adv_bulk_resolution.py`: 7 passed. Full `tests/mdm/`
suite and full repo suite both re-run and green after the above test
changes (see PR for the exact counts). No image rebuild required for the
test-file diff itself, but this change is real production code
(`edgar_warehouse/mdm/adv_bulk.py`), so it **does** need a warehouse image
rebuild + `mdm` role redeploy before the fix is live, and the next
`mdm run --entity-type fund` (or `--entity-type all`) after that deploy
will be the one that pays the ~130,614-fund one-time backlog sized above —
expect that specific run to take longer and write substantially more than
a typical incremental run; this is expected, not a regression.
