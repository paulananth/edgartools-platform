# 27 — Contract legacy acquisition bypasses

**What to build:** Remove the obsolete direct acquisition and legacy dispatch
paths after every supported family has demonstrated the authoritative path,
leaving one enforceable route from decision through verified Bronze and
published processing status.

**Blocked by:** 21 — Migrate submissions snapshots and pagination; 22 — Migrate
company-facts snapshots; 23 — Migrate reference catalogs; 24 — Migrate ADV
sources; 25 — Add conflict, repair, exclusion, and evidence-import workflows;
46 — Wire `filing_artifact`'s gated driver into `daily_incremental`

**Status:** claimed (2026-08-29, grok — first family slice: `filing_artifact` /
OWNERSHIP_FORMS only). Ticket 26 removed from
this ticket's blockers — [Ticket 10](10-decide-migration-cutover-rollback.md)'s
Decision 5 found it was never a genuine prerequisite (ordinary per-family
cutover doesn't route through Ticket 26's rebuild machinery at all). Ticket
24's bullet 4 (`adv_filing` had no discovery driver) is now fully resolved,
not partial. Ticket 22 (bullets 1/4/5) and Ticket 23 (bullet 1) still carry
named partial bullets, but per this map's established convention (see
Ticket 26's own prior correction) a `resolved`-prefixed status satisfies
blocking regardless of partial detail — every listed blocker is resolved.
**Corrected again 2026-08-27:** the "worth resolving before starting" note
above has been resolved by actually starting — live investigation into how
to wire `filing_artifact` into a real schedule (Ticket 10's Decision 4)
found the mechanism substantially more delicate than either this ticket or
Ticket 10 assumed (`daily_incremental`'s Step Function definition has
SEC-fetch lease acquisition/release, refresh-mode branching, and deferred-
execution handling — the same state machine behind two prior documented
incidents in CLAUDE.md). That concrete first slice — wiring one family's
driver into one schedule, the prerequisite for this ticket's own removal
work to have any real evidence to act on — is split out as its own ticket:
[46 — Wire `filing_artifact`'s gated driver into `daily_incremental`](46-wire-filing-artifact-into-daily-incremental.md).
This ticket (27) now additionally depends on 46's outcome for its own
bullets to be actionable — its removal-evidence bullets cannot be attempted
for any family until that family has been through a real Decision-2
side-by-side window, and none has yet. The compare harness itself is
[Ticket 51](51-build-filing-artifact-capture-parity-harness.md); 27 still
needs a live window that *passes* that harness, not merely the code.
[Ticket 52](52-check-harness-exercises-legacy-capture.md) found Ticket 51
is compare-only: it never runs the legacy artifact pipeline. The missing
dual-path *run* is [Ticket 53](53-drive-legacy-and-gated-capture-into-parity-diff.md).

- [ ] Architecture tests prove every approved low-level source adapter is
  reachable only through the ledger-gated Facade.
- [ ] Every required Source Family Registry entry supplies complete executable
  discovery, fetch, completeness, and required-producer policies.
- [ ] Every acquisition command binds execution, scope resolution, and planned
  writes in one validated registration; legacy acquisition dispatch is gone.
- [ ] Persisted lifecycle remains enforced by PostgreSQL constraints and a
  deterministic reducer or transition table rather than GoF State objects.
- [ ] Durable delivery remains a transactional outbox rather than Observer
  callbacks, and no unproven Template Method hierarchy is introduced.
- [ ] End-to-end and rollback evidence prove removal leaves no unsupported
  family, unauthorized network path, or partial serving state.

## Answer

**First family slice only (`filing_artifact` / OWNERSHIP_FORMS). Remaining
bullets stay open.** Ticket 10 Decision 1 is per-family; Decision 2 for this
family is the Ticket 53 live Apple Form 4 dual-path pass (2026-08-29, date
`2026-08-27`, CIK `320193`). This slice retires that family's *scheduled*
legacy fetch without deleting the code (Decision 6).

**What shipped**
- `daily-incremental` CLI default is now `--enable-filing-artifact-gated-capture`
  on. Scheduled ECS/ASL is unchanged (`States.Array('daily-incremental', ...)`)
  and therefore picks the new default up with no state-machine redeploy of the
  flag itself — a warehouse image rebuild is still required for the Python to
  land. `--disable-filing-artifact-gated-capture` is the Decision 6 rollback:
  gated off, OWNERSHIP_FORMS return to the legacy pipeline.
- While gated is on, `_run_submissions_bronze_then_silver` passes
  `skip_ownership_forms=True`, so `_configured_parser_accessions` unregisters
  Form 3/3A/4/4A/5/5A from the legacy artifact loop. ADV, 13F, and Item 5.02
  8-K stay on legacy. `fetch_filing_artifacts` remains importable.
- Gated capture now **fails closed**. Ticket 46 isolated failures because it
  was an off-by-default side channel riding a `MaxAttempts: 3` budget. After
  cutover, swallowing the error would skip ownership in legacy *and* drop the
  family's capture. Partial daily-index loads still skip gated (nothing newly
  sealed to drive) **and keep the legacy ownership fetch** — skipping both
  would drop Form 3/4/5 for that window.

**What this slice deliberately does not do**
- Does not cut over ADV / 13F / 8-K / submissions / company_facts /
  reference_catalog. Those families have not passed Decision 2.
- Does not wire gated capture into `load_history` / `bootstrap-next` (Ticket 10
  Decision 4 named both schedules; Ticket 46 only wired `daily_incremental`;
  this slice stays on that same schedule).
- Does not delete `fetch_filing_artifacts` or `_run_configured_form_artifact_pipeline`.
- Does not add GoF State objects, Observer outbox, or a Template Method
  hierarchy. Cutover is a boolean plus a form-set filter.
- Does not claim the six ticket bullets. Architecture-test-all-adapters,
  complete registry policies for every family, and "legacy dispatch is gone"
  remain follow-up work after each remaining family's Decision 2 pass.

**Rollback:** `--disable-filing-artifact-gated-capture` on the existing
`daily-incremental` command. Deletion of the dormant `fetch_filing_artifacts`
path is a follow-up commit after one full scheduled cycle, per Decision 6.

**Handoff note (2026-08-31/09-01):** this slice was originally grok's
uncommitted, in-progress work; per explicit user instruction it was copied
into a new `claude/change-propagation-ticket27-legacy-bypasses` branch to
finish and land, leaving grok's own worktree/branch untouched. The naive
first copy attempt (a wholesale file overwrite) silently reverted unrelated
tickets that had merged to `main` since grok's branch point — caught before
committing, and redone correctly via `git diff HEAD` (grok's real patch) +
`git apply --3way` against current `main`. Two genuine merge conflicts were
found and resolved: the gated-capture call site and its test needed the
`bookkeeping` argument that a later, unrelated ticket had made required on
`_run_filing_artifact_gated_capture` after grok's branch point (grok's patch
predates that signature change); the 3-way merge also silently dropped an
`as gated_capture` context-manager binding in the test file outside any
marked conflict region, caught only because a later assertion would
otherwise NameError. Three-axis review (Standards/Spec/GoF, CLAUDE.md hard
rule) ran before committing: Spec and GoF both came back clean (GoF
explicitly confirmed the new `skip_ownership_forms` parameter threading is
symmetric with this function's own established growth pattern, not a new
problem); Standards found one real duplication — the gated-capture
enablement condition was computed twice, ~15 lines apart — fixed by
extracting it to a single `gated_capture_enabled` local used both to
compute `skip_ownership_forms` and to gate the dispatch call itself, so the
two can't silently diverge. 44 targeted tests pass; a broader
`tests/unit/ tests/application/ tests/architecture/` sweep found 1 failure,
confirmed pre-existing and unrelated (a UTC month-rollover date flake in an
untouched ADV bulk dataset test, reproduced identically on a clean `main`
checkout). mypy: zero new errors (29 pre-existing, byte-identical against
clean `main`).
