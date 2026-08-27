# Decide baseline, migration, cutover, and rollback sequencing

Type: grilling
Status: resolved
Blocked by: 09

## Question

How should production move from the current full-scan/mutable-key paths to the
Change Propagation Run contract without a full bronze replay, concurrent
canonical writers, lost changes, or an unrollbackable consumer split?

Decide baseline inventory and cursor seeding, read-only reconciliation,
boundary-by-boundary cutover order, treatment of in-flight executions, links to
the open Snowflake-silver/dbt-gold/DuckDB-retirement work, feature-flag or
task-definition revision boundaries, rollback watermark rules, and retention
of superseded DuckDB, mutable landing, and legacy SOURCE artifacts. Every
operator step must be committed, repeatable, and secret-safe.

## Answer

Grilled 2026-08-27, grounded against live prod state rather than the map's
original 2026-08-21 assumptions — a lot changed underneath this question in
the intervening 30+ resolved tickets. Two facts resolved by direct
investigation, not decision:

- **The new ledger-gated drivers have zero live scheduled presence today.**
  Checked `infra/scripts/deploy-aws-application.sh` directly: only
  `load-daily-form-index-for-date` (the sealing step) appears in any real
  state machine. `load_history`/`daily_incremental` still exclusively call
  the legacy `bootstrap-next` → `fetch_filing_artifacts` path for every
  family, including `filing_artifact` itself — Ticket 29's dry run was a
  one-off manual invocation, not a running schedule. "Cutover" therefore
  means *first-ever* wiring, not flipping an existing parallel system.
- **In-flight executions need no special handling.** AWS Step Functions
  pins an execution to the state-machine definition active at
  `StartExecution` time; a later `UpdateStateMachine` never affects an
  already-running execution. The ticket's "treatment of in-flight
  executions" sub-question is resolved by this platform guarantee, not a
  new design.

**Decisions (all accepted by the operator):**

1. **Cutover unit is per-family, independent** — not a single coordinated
   `Baseline Coverage Contract`/`Ledger Epoch` activation across every
   family at once. `CONTEXT.md`'s epoch/baseline language is scoped to
   initial bootstrap or disaster recovery (Ticket 26's literal title), not
   steady-state migration onto an already-healthy, already-running ledger.
   A coordinated whole-platform cutover would gate everything on the still-
   partial `company_facts`/`reference_catalog` bullets for zero interim
   benefit.
2. **Verification gate before retiring a family's legacy capture call**
   (Ticket 27's job): run both paths side-by-side for at least one full
   production window, then diff their captured-artifact sets for that
   window. Retirement requires an equal-or-superset result with zero silent
   gaps — not merely a single successful dry run (which Ticket 29 already
   proved is possible, but proved in isolation, never against the legacy
   path's own output for the same window).
3. **No Ticket 26 baseline rebuild for ordinary cutover.** A family starts
   capturing forward from now, on top of its already-trusted existing
   bronze/silver data. Ticket 26's full Hybrid Source Baseline rebuild is
   reserved strictly for genuine ledger loss/reinitialization — not a
   mandatory step for migrating a healthy, already-loaded family onto the
   new path.
4. **Cutover mechanism:** wire `drive-<family>-discovery` into the
   *existing* `daily_incremental`/`load_history` state machines, replacing
   that family's `bootstrap-next` artifact-fetch call, once bullet 2's
   side-by-side verification passes for that family. No new, separate
   schedule — reuses the proven scheduling/retry/concurrency
   infrastructure already in place.
5. **Ticket 26 no longer blocks Ticket 27.** Decision 3 means ordinary
   per-family cutover never routes through Ticket 26's machinery at all, so
   it was never a genuine prerequisite for retiring legacy bypasses — only
   an artifact of the map's original, pre-implementation framing. Removed
   from Ticket 27's `Blocked by` list (see that ticket's own file). Ticket
   26 remains a legitimate, separate piece of disaster-recovery machinery,
   just off Ticket 27's critical path.
6. **Data retention (DuckDB/mutable landing/legacy SOURCE artifacts) is out
   of this ticket's scope entirely**, deferred to the already-charted,
   already-open [DuckDB Retirement map](../../duckdb-retirement/map.md),
   which explicitly owns "cutover/rollback mechanics" for the storage
   layer — re-deciding it here would violate this map's own "settled
   predecessor maps are inputs, not questions to reopen" rule. This
   ticket's own rollback rule is narrower and code-only: a family's legacy
   capture call/code path stays dormant (unregistered from the schedule,
   not deleted) for one full cycle after cutover, deleted only in a
   follow-up commit — cheap, git-revertable rollback without inventing a
   watermark mechanism. Coordination between this map's acquisition-path
   cutover and DuckDB Retirement's storage-layer cutover is tracked
   separately as new
   [Ticket 45](45-coordinate-with-duckdb-retirement-cutover.md).

**What this unblocks:** Tickets 26 and 27 were, until this resolution, both
transitively blocked on this ticket alone (every other listed blocker for
each — 09, 21, 22, 23, 24, 25 — was already resolved). Both are now open,
unblocked, unclaimed — see their own files for corrected `Blocked by`/
`Status` lines.
