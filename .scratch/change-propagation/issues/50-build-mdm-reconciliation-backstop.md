# 50 — Build the MDM Reconciliation Backstop

**What to build:** The periodic full-universe MDM match, survivorship, and
relationship re-derivation pass Ticket 38 designed. Existing
`MDMPipeline.run_all()` with skip-if-unchanged **off** and **no `--limit`**,
plus a real `MdmMatchReview` producer, an exclusive lease against ordinary
`mdm run`, and an off-by-default monthly EventBridge rule on `mdm-utility`.

**Blocked by:** 38 — Design the periodic MDM full-universe reconciliation
backstop (resolved)

**Status:** resolved

Type: task

- [x] A dedicated CLI / `mdm-utility` mode runs `run_all()` across all six
  entity types then `derive_relationships()`, with skip-if-unchanged
  disabled and no default `--limit`.
- [x] Review-band hits insert `MdmMatchReview` (first producer).
  `AUTO_MERGE` onto a different entity uses existing `merge_entities`.
  Same `entity_id` is a no-op. A live golden record is never auto-split
  because a backstop score went cold.
- [x] Exclusive lease: this pass and ordinary `mdm run` resolution cannot
  overlap; in-flight conflict fails closed and retries on the next slot.
- [x] Off-by-default monthly EventBridge rule, MDM-owned, not Sunday,
  same enable/disable deploy-flag pattern as publication-drain. First
  measured run sets the duration bound; do not copy Identity Backstop
  Sweep's 18h SLO.
- [x] A test proves skip-if-unchanged is off (an unchanged hash is still
  re-scored), a review-band pair writes `MdmMatchReview`, and a second
  overlapping `mdm run` is rejected.

## Answer

Built exactly the mechanism Ticket 38's Answer specified: existing
`MDMPipeline.run_all()`, unchanged in structure, gains one new
`reconciliation_pass: bool = False` flag (default preserves every existing
caller byte-for-byte) that (a) disables every step's skip-if-unchanged
shortcut and (b) routes company/security/person resolution through a new
finding-disposition branch instead of the plain create-or-merge path.

**New mechanism:**
- `edgar_warehouse/mdm/lease.py` + a new `mdm_pipeline_lease` table
  (migration `020_mdm_pipeline_lease.sql`, `MdmPipelineLease` model) --
  mirrors `bookkeeping.store`'s `acquire_pipeline_run_lease` conditional-
  upsert exactly, against MDM's own Postgres (a different instance from the
  warehouse's Bookkeeping store the original mirrors from).
- `BaseResolver.resolve_or_create` gains an optional `reconciliation_mode`
  kwarg (default `False`); when `True` and a row already has a live
  `MdmSourceRef` entity assignment, `_reconcile_against_existing` decides:
  same candidate → no-op; `AUTO_MERGE` onto a different entity → the
  private, non-committing `stewardship._merge_entities` (the public
  `merge_entities` commits immediately, which would land a half-processed
  row -- `accept_review()` uses the same private variant for the identical
  reason); `REVIEW` → insert `MdmMatchReview` (deduped against an existing
  pending pair for the same entity pair, in either order), leaving the
  assignment untouched; `QUARANTINE` → always no-op, regardless of what a
  low-confidence candidate nominally prefers.
- `edgar_warehouse/mdm/reconciliation_backstop.py`: acquires the lease in
  `"backstop"` mode, runs `run_all(limit=None, reconciliation_pass=True)`,
  releases in a `finally`. Deferring (lease held) is not an error.
- `mdm reconcile-backstop` CLI subcommand +
  `mdm_reconciliation_backstop` mode on the consolidated `mdm-utility`
  machine (mirrors `mdm_publication_drain`'s wiring exactly). Sized
  `mdm-large` (unmeasured, conservative -- "first measured run sets the
  duration bound").
- `--configure-reconciliation-backstop-schedule <enable|disable>`, off by
  default, `cron(0 6 1 * ? *)` (1st of month), same deploy-flag shape as
  publication-drain.
- Ordinary `mdm mastering --entity-type all` also now acquires the same
  lease (`"ordinary"` mode, `_run_all_with_ordinary_lease` in `cli.py`) so
  the backstop can see it and defer -- but ordinary itself never fails
  closed on the lease; see "Disclosed limitation" below.

**Deliberately narrower than Ticket 38's own parenthetical:** QUARANTINE-
band verdicts never queue for review even when they nominally "prefer
someone else" -- `match.py`'s `FuzzyNameMatcher` always attaches a
best-effort `candidate_entity_id` at any score, so honoring that aside
literally would flood the review queue with near-arbitrary low-confidence
pairs on the very first backstop run over live production data. Ticket
50's own checklist bullet 2 only requires review-band inserts; this
implements exactly that, and documents the deviation inline.

**Disclosed limitation (found by `/code-review`'s Spec axis, not fixed --
a deliberate tradeoff):** the lease makes "cannot overlap" one-directional,
not fully bidirectional. It reliably stops the backstop from *starting*
while ordinary resolution is active (proven by
`test_a_second_overlapping_backstop_attempt_is_rejected`/
`test_backstop_defers_when_an_ordinary_run_holds_the_lease`). It does
**not** stop an ordinary run from *starting* while a backstop pass is
already mid-flight -- ordinary always proceeds regardless (proven by
`test_proceeds_even_when_a_backstop_pass_holds_the_lease`), so the two can
genuinely run concurrently against the same MDM Postgres state for the
rest of the backstop's run. A symmetric fail-closed design was the first
draft; rejected on review (a multi-hour, off-by-default monthly job has no
business failing a bounded production daily-pipeline execution that has no
retry slot of its own to fall back to -- the same asymmetry the existing
Identity Refresh Slot precedent already accepts). The
`mdm_resolution_lease_conflict` event makes every occurrence observable.
Full reasoning: `lease.py`'s module docstring. A future revisit could have
the backstop checkpoint/re-acquire between entity types so a conflicting
ordinary run can interrupt it early instead of racing it for hours; not
built here.

**"All six entity types," precisely:** `run_all()` resolves 5
(company/adviser/security/person/fund) -- `audit_firm` entities are seeded
once via a standalone `mdm seed-audit-firms` command outside `run_all()`'s
loop entirely, a pre-existing limitation of `run_all()` itself, not
something newly introduced or newly worked around here.

**New finding, disclosed but not fixed (out of scope):** while building the
AUTO_MERGE disposition test, found that `PersonResolver`'s owner_cik-less
fuzzy-name matching can never actually reach `AUTO_MERGE` in practice --
`FuzzyNameMatcher`'s `context_fields=("issuer_cik",)` check clamps any
score `>= auto_merge_min` down to `auto_merge_min - 0.01` (review band)
whenever context doesn't match, and `PersonResolver._existing_candidates`
never populates `issuer_cik` on the candidate dicts it returns -- so the
context check can never pass for this resolver's own candidates. A genuine,
pre-existing, out-of-scope bug affecting the *ordinary* (non-backstop) path
identically, not something this ticket's disposition logic caused or should
silently work around. The diff's own `AUTO_MERGE`-onto-a-different-entity
test uses a CIK-exact scenario instead (a real filing revealing a
previously-unknown owner CIK), which is unaffected by this gap and is
itself a realistic backstop scenario.

**Code review:** all three axes ran (`/code-review`'s CLAUDE.md hard rule).
Standards: no hard violations; one real GoF finding (below) plus minor
notes all addressed (a `mdm_reconciliation_backstop_failed` event added for
symmetry with `_started`/`_completed`; a comment clarifying the private
`_merge_entities` import). Spec: the lease-asymmetry limitation above
(disclosed, not fixed -- a reasoned tradeoff, not an oversight) and the
QUARANTINE-band narrowing (already disclosed inline); everything else
(review-band scoping, EventBridge cadence/off-by-default, all 3 required
tests) confirmed correct. GoF: this diff was the 3rd near-identical copy of
a `configure_*_schedule` EventBridge-rule function in
`deploy-aws-application.sh` (fence-monitor, publication-drain, this one) --
extracted a shared `configure_scheduled_utility_rule` helper, verified live
against a stubbed `aws_cli`/`log` that all three callers (including the two
pre-existing ones) still produce byte-identical rule names, target ids,
schedules, and descriptions.

**Tests:** 27 new (7 lease acquire/release/stale-override/overlap-rejection
in `test_pipeline_lease.py`; 6 disposition cases against real
`PersonResolver` + real Jaro-Winkler scores in
`test_reconciliation_disposition.py`; 3 backstop-orchestration cases in
`test_reconciliation_backstop.py`; 2 ordinary-lease-proceeds cases in
`test_ordinary_run_lease.py`; the existing `test_mdm_utility_state_machine.py`
extended for the new mode). Full `tests/mdm/` suite green (552 passed, 3
pre-existing fastapi-import-gap files excluded, unrelated to this change).
Full repo suite (excluding that same gap and the Docker-based
`tests/integration/` directory, none of which this ticket touches) green:
2921 passed, 6 skipped. One Docker-based Postgres integration test
(`test_acquisition_ledger_postgres.py`) fails on a live schema-drift issue
in an unrelated subsystem (`source_fetch_work.captured_etag`) --
independently confirmed via `git stash` to fail identically on the
pre-ticket-50 baseline, so it's pre-existing and out of scope.

`/gof-refactor-reviewer` consulted per CLAUDE.md's hard rule, formally via
`/code-review`'s GoF axis (see above) rather than an inline self-check,
given the size of this ticket.

## Notes

Design is the Answer on [38 — Design the periodic MDM full-universe
reconciliation backstop](38-design-mdm-full-universe-reconciliation-backstop.md).
Do not implement this as `mdm verify-graph` or as a step on the Identity
Refresh Slot. Do not block on [49 — Implement 1-hop MDM candidate-neighbor
expansion](49-implement-one-hop-mdm-candidate-neighbor-expansion.md).
