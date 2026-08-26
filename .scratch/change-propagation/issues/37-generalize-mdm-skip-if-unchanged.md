# 37 — Generalize the domain-content-hash skip-if-unchanged path to every MDM entity type

**What to build:** Give adviser, person, security, fund, and audit-firm
resolution the same skip-if-unchanged fast path `run_companies` already
has, using the already-generic `MdmSourceRef.source_content_hash` column.

**Blocked by:** None — the schema is already generic; the decision to
generalize is already made (Ticket 06).

**Status:** resolved

- [x] Confirm, per entity type, whether its resolver already reads/writes
  `source_content_hash` to skip unchanged rows — this was not fully audited
  while resolving Ticket 06, only confirmed true for `run_companies`.
- [x] For every entity type found not to have it, wire the same
  skip-if-unchanged check its resolver already has for match/survivorship,
  keyed on `source_content_hash` comparison against the stored value from
  the prior resolution.
- [x] A test per entity type proves an unchanged source row is skipped
  (no new `MdmChangeLog` row, no re-resolution work) while a changed row
  still resolves normally.

## Notes

Surfaced while resolving [06 — Decide MDM affected-key closure and
publication outbox](06-decide-mdm-closure-and-outbox.md) — see that
ticket's Answer. `source_content_hash` lives on the entity-type-generic
`MdmSourceRef` table (keyed to `mdm_entity`, not to any one entity type),
so this is wiring per resolver, not a schema change.

## Answer

**No new wiring was needed — a separate, already-merged map
([`mdm-resolver-skip-unchanged`](../mdm-resolver-skip-unchanged/map.md),
its own dedicated audit) had already closed bullets 1 and 2 for every
resolver reachable from a live `mdm run`, before this ticket existed.** The
gap Ticket 06's Answer flagged ("only confirmed true for `run_companies`")
was stale by the time this ticket was picked up. Per entity type:

| Entity type | Mechanism | Status |
|---|---|---|
| company | `CompanyResolver._skip_if_unchanged`, content-hash on `MdmSourceRef.source_content_hash` | Already live (single-path-per-layer map, Ticket 03); tested in `tests/mdm/test_run_companies_skip_unchanged.py` |
| person | Same content-hash mechanism, `PersonResolver.resolve_one` | Already live (`mdm-resolver-skip-unchanged` map, Ticket 02, commit fixing an append-only-staging gap); tested in `tests/mdm/test_run_persons_skip_unchanged.py` |
| security | Same content-hash mechanism, `SecurityResolver.resolve_one` | Already live (commit `091809b0`, the fix the whole `mdm-resolver-skip-unchanged` map was named after); tested in `tests/mdm/test_run_securities_skip_unchanged.py` |
| adviser | Existence-based dedup in `adv_bulk.py`'s `resolve_advisers_bulk` (`_existing_source_ids`, keyed on `accession_number`) — the live path; `AdviserResolver` (the content-hash-shaped class) is dead code, deleted | Already live; **newly tested this session** — added `test_adviser_bulk_resolution_a_new_accession_for_the_same_crd_still_resolves` to close the "changed row still resolves" half this ticket's bullet 3 required, which had no prior test |
| fund | Existence-based dedup in `adv_bulk.py`'s `resolve_funds_bulk` (same `_existing_source_ids` mechanism, keyed on `private_fund_id` when present); `FundResolver` is dead code, deleted | Already live for the "unchanged row skipped" half; **newly tested this session** — added `test_fund_bulk_resolution_second_identical_run_does_not_duplicate_stage_or_change_rows` (restart-idempotency, parity with adviser's existing equivalent test). Writing the "changed row still resolves" test for fund (bullet 3's other half) surfaced a real, different gap — see below |
| audit_firm | `MDMPipeline._audit_firm_entity_id`, a plain get-or-create keyed on `pcaob_firm_id`/name during relationship derivation, not a row-loop resolver | Not applicable — there is no append-only staging or per-row resolution work to skip; the existence check (`session.get(MdmEntity, entity_id) is None`) already is the skip mechanism, and it's inherently bounded (one entity created once, ever, per PCAOB id) |

**Real gap found while writing this ticket's own required tests, filed
separately:** proving fund's "a changed row still resolves normally" half
(bullet 3) with a live test revealed that `resolve_funds_bulk`'s dedup key
is `private_fund_id` when present — not `accession_number` the way adviser
is. A later accession amending an already-known pfid is treated as
"already seen" by the dedup check, so it silently produces no new
`MdmSourceRef`/stage/`MdmChangeLog` row (even though the golden `MdmFund`
record itself still refreshes correctly via the unconditional `setattr`
loop). Since `MDMExporter.export_pending` selects work via
`MdmChangeLog.exported_at IS NULL`, this means a fund's real attribute
changes on a later ADV amendment never get flagged for re-export to
Snowflake gold — a genuine freshness bug, not just an audit-trail gap.
This is a *different* bug shape than the one this ticket targets (too
little dedup causing unbounded growth vs. too much dedup dropping change
signal — the inverse), and fixing it means re-keying dedup to
accession-based and sizing a real one-time re-stage backlog across the
live fund population first (unsized as of this entry) — not a same-session
line edit. Filed as
[42 — Fund bulk resolution's pfid-keyed dedup starves MDM export of change
signal](42-fund-dedup-keyed-on-pfid-starves-mdm-export.md); the current,
surprising behavior is locked in as a characterization test,
`test_fund_bulk_resolution_dedups_by_private_fund_id_not_accession`, so
whoever fixes Ticket 42 has a test that goes red the moment the fix lands.

**Lesson, same shape as CLAUDE.md's stub-fixture entry
("INSTITUTIONAL_HOLDS / EMPLOYED_BY" 5-whys) landing in a new subsystem:**
`mdm-resolver-skip-unchanged`'s own conclusion that adviser/fund's bulk
mechanism was "a different, arguably stronger mechanism than content-hash
skip" was reached by *reading* `adv_bulk.py`, not by a live test proving
both halves of the required behavior. It was right about adviser and half
right about fund — the untested half was exactly where the gap was
hiding. This ticket's own bullet 3 ("a test per entity type") is what
caught it; a documentation-only audit would not have.

Full test coverage added this session:
`tests/mdm/test_adv_bulk_resolution.py` — 3 new tests (adviser new-accession
proof, fund restart-idempotency proof, fund characterization test), all
passing alongside the 4 pre-existing tests in that file (7 total).
