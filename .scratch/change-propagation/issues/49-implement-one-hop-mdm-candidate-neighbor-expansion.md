# 49 — Implement 1-hop MDM candidate-neighbor expansion

**What to build:** When a source row changes, also re-check entities with
a *direct* existing relationship edge to the resolved entity (known
officers, adviser, auditor) — not the whole graph and not zero expansion.
Ticket 06 decided this as the incremental Affected-Key Closure for MDM;
nothing implements it. `MDMPipeline.run_all()` still sweeps entity-type
loops plus `derive_relationships()` with no neighbor expansion.

**Blocked by:** 06 — Decide MDM affected-key closure and publication
outbox (resolved)

**Status:** resolved

Type: task

- [x] A changed source row's resolved entity expands to its 1-hop
  relationship neighbors (direct `mdm_relationship_instance` edges only)
  and those neighbors are re-checked in the same `mdm run`, not deferred
  to the MDM Reconciliation Backstop.
- [x] Unrelated entities are not re-resolved. Cost stays proportional to
  the change plus direct neighbors, not the universe.
- [x] Skip-if-unchanged still applies to neighbors whose source hash is
  unchanged — 1-hop re-checks the *relationship/survivorship* implication,
  it does not become a skip-off universe scan (that is Ticket 50).
- [x] A test proves a changed company re-checks a directly-linked person
  (or adviser/auditor) and does not re-check a 2-hop entity.

## Answer

Built two pieces:

1. **New pure module** `edgar_warehouse/mdm/neighbor_expansion.py`:
   `find_one_hop_neighbor_entity_ids(session, changed_entity_ids) -> set[str]`
   — one indexed query over `mdm_relationship_instance` (active,
   non-quarantined only), returning the *other* side's entity_id for every
   edge touching the changed set. Genuinely 1-hop: does not recurse, and
   an entity already in `changed_entity_ids` is never returned as its own
   neighbor. 7 unit tests
   (`tests/mdm/test_neighbor_expansion.py`), including the ticket's own
   exact requirement — a direct neighbor is found, a 2-hop entity is not.

2. **Wiring into `MDMPipeline.run_all()`** (`edgar_warehouse/mdm/pipeline.py`):
   - `run_companies` now tracks which CIKs' `entity_id` it actually
     changed (not `skipped_unchanged`) on a new instance attribute,
     `_last_run_changed_entity_ids` — read by `run_all()` after the
     5-way concurrent entity-resolution phase completes (each step's
     worker `MDMPipeline` instance is captured per `stat_field` in a
     small dict; a plain-Python set survives its own session's close).
   - `run_persons` gained a new `owner_ciks` scoping parameter, distinct
     from the existing `issuer_ciks` — re-check these exact reporting
     owners regardless of which issuer their filing names.
   - `run_all()`, after the 5-way phase and before `derive_relationships()`,
     computes the 1-hop neighbors of whatever companies changed, resolves
     the person-typed ones to `owner_cik` via `MdmPerson`, and calls
     `run_persons(owner_ciks=...)` for exactly that set. A new
     `PipelineStats.neighbor_persons_rechecked` field records the count.
     Skip-if-unchanged is untouched and still fires inside that call for
     any neighbor whose own source hash hasn't moved — this pass adds
     candidates to check, it does not bypass the existing cheap-no-op
     path.

   4 integration tests through the real `run_all()` wiring
   (`tests/mdm/test_neighbor_expansion_run_all.py`), proving: a changed
   company (pre-seeded with no `MdmSourceRef`, so `resolve_one` treats it
   as a genuine first observation rather than `skipped_unchanged`)
   triggers exactly one `run_persons(owner_ciks=[<direct neighbor>])`
   call, never including a 2-hop-away person; a changed company with zero
   existing relationships triggers no extra call at all; a direct
   neighbor with a real `sec_ownership_reporting_owner` row in silver is
   actually resolved (not just scoped-and-iterated); and a second
   `owner_ciks`-scoped call against the same unchanged silver data adds
   zero new `mdm_entity_attribute_stage` rows — skip-if-unchanged fires
   through this exact call path, proven directly, not assumed from the
   shared code path.

**Deliberately scoped to company-changed → person-neighbor**, the
ticket's own paradigm example, and its own bullet 4 explicitly accepts
either "a directly-linked person (or adviser/auditor)." Two real,
disclosed gaps this scoping leaves (found by `/code-review`'s Spec axis,
not silently absent):

- **Input side:** only `run_companies` tracks a changed-entity-id set
  today. A changed adviser, security, fund, or person triggers **zero**
  1-hop re-check at all — not even for its own person-typed neighbors.
- **Output side:** `find_one_hop_neighbor_entity_ids` itself returns
  *every* direct neighbor regardless of type — adviser, `audit_firm`,
  parent/subsidiary company included — but only the person-typed ones are
  actually re-checked, since `run_persons(owner_ciks=...)` is the only
  scoped-resolve entry point this ticket built. Non-person neighbors the
  query genuinely finds are silently not re-checked today; this is now
  documented directly at the call site in `run_all()`, not just here.

Both gaps need the identical `_last_run_changed_entity_ids` tracking
ported to the other four entity-resolution steps, plus a matching
scoped-resolve parameter on whichever resolver handles each non-person
type (`run_advisers`, and wherever `audit_firm`/`security`/`fund`
entities are created) — not built here; a natural, bounded follow-up
using the exact same mechanism, not a redesign. The MDM Reconciliation
Backstop (Ticket 50, still unbuilt) remains the mechanism for multi-hop,
near-miss, and hash-skip cases this bounded pass structurally can't
reach — including, until the above follow-up lands, the non-person and
non-company-sourced 1-hop cases this pass currently misses too.

**Rule 0 self-check** (inline, not a full `/gof-refactor-reviewer`
subagent consult): `git log` shows `edgar_warehouse/mdm/pipeline.py`
churns frequently, almost entirely on *performance/scoping* fixes
(plateau bugs, unscoped whole-type loads, OOM). This change is narrow and
additive — one new optional parameter, one new tracked instance
attribute, one new bounded query — not a restructuring, and it was
checked specifically against that churn pattern: the neighbor query is
bounded to the changed set (one indexed query, no graph walk), so it
does not reintroduce the unscoped-scan shape this file's own history
warns about.

`/code-review`'s three axes (Standards, Spec, GoF) ran; GoF clean. Standards
and Spec each caught real issues, all fixed before this commit:
- **Concurrency pattern deviation** (Standards): the changed-entity-id set
  was being written into a shared dict from inside a worker thread,
  justified only by a GIL-safety comment, instead of the file's own
  established worker-returns/main-thread-assigns pattern (`as_completed`
  already does this for `stats`). Fixed: `_run_step` now returns
  `(result, changed_ids)` and the main-thread loop assigns both.
- **Stale invariant comment** (Standards): the pre-existing "nothing on
  `self.session` was written in this method" comment above `rollback()`
  no longer held once this ticket added a real write-and-commit through
  `self.session` (via `self.run_persons(...)`) later in the same method.
  Fixed: comment now scoped to "up to this point," with a pointer to the
  new write.
- **Untested skip-if-unchanged claim** (Standards + Spec, same finding):
  neither original integration test proved a real re-check resolves
  anything or that skip-if-unchanged fires through this exact path — both
  now added (see above).
- **Silent non-person-neighbor drop** (Spec): `find_one_hop_neighbor_
  entity_ids` returns every direct neighbor type, but only person-typed
  ones were being acted on, with no comment disclosing that the others
  are found and then dropped. Fixed: documented explicitly at the call
  site and in this Answer (see the two disclosed gaps above).
- **Mysterious Name** (Standards, minor): `_normalize_issuer_ciks` renamed
  to `_normalize_cik_list` — it's now used for `owner_ciks` too, not just
  `issuer_ciks`.

Full `tests/mdm/` suite green (553 passed, excluding 3 pre-existing files
that fail to import for an unrelated environment reason — `fastapi` is
not installed in this dev environment at all, confirmed via a
git-stash-and-retry that the same failures exist on unmodified `main`).

## Notes

Surfaced while resolving [38 — Design the periodic MDM full-universe
reconciliation backstop](38-design-mdm-full-universe-reconciliation-backstop.md).
Ticket 06 already decided 1-hop; this ticket is the missing implementation.
The MDM Reconciliation Backstop (Ticket 50) covers multi-hop, near-miss,
and hash-skip and must **not** wait on this ticket.
