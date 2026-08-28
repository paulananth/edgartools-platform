# Inventory Every Production Workflow and Consumer

Type: research
Status: resolved
Blocked by: 01

## Question

For every live `edgartools-prod-*` Step Functions state machine, what triggers
it, which ECS commands and task-definition revisions does it invoke, which
outputs or integrity claims does it produce, who or what consumes those
outputs, how often is it executed, and what are its recent success, failure,
retry, and duration distributions?

Identify overlapping wrappers, duplicate MDM chains, one-off repair workflows,
operator utilities, scheduled production paths, and workflows with no observed
execution or downstream consumer. Bind the inventory to the post-Claude state
machine definition, immutable image digests, execution-history window, and
output evidence. Surface facts only; keep, merge, and retirement decisions
belong to the workflow-portfolio ticket.

## Draft inventory for audit

The complete source and live-AWS draft is in
[`production-workflow-consumers-source-trace-2026-08-10.md`](../research/production-workflow-consumers-source-trace-2026-08-10.md).
This ticket intentionally remains open until an independent audit accepts the
inventory and output-level evidence.

The draft currently establishes:

- all 26 live production state-machine definition revisions and canonical ASL
  hashes;
- all current ECS task-definition revisions, CPU/memory settings, immutable
  warehouse and MDM image digests, and normalized ECS command operations;
- 114 parent executions in the 30-day window: 39 succeeded, 57 failed, and 18
  aborted;
- 81 Step Functions task retry attempts across 34 executions, with no parent
  execution redrives;
- no current EventBridge rule or EventBridge Scheduler schedule for the
  production portfolio, despite repository support for daily and backstop
  `daily-incremental` rules;
- repository-proven Snowflake, dbt, dashboard, operator, and workflow-to-
  workflow consumers, with inferred and unknown consumers labeled separately;
  and
- nine live workflows with no execution in the window, seven ordinary MDM
  composite paths whose new graph candidate has no proven active consumer,
  and one standalone generation workflow with no evidenced external consumer.

These are inventory facts, not keep, merge, reshape, schedule, or retirement
decisions.

## Audit gates before resolution

1. ~~Independently rerun the read-only definition, task, schedule, execution, and
   history capture and reproduce the 26-workflow coverage and aggregate counts.~~
   **Done 2026-08-11.** Rerun from scratch (fresh `list-state-machines`,
   `describe-state-machine`, `describe-task-definition`, `describe-images`, plus
   git history and source-comment cross-checks) — reconfirms the 25 live
   `edgartools-prod-*` machines and the 7-machine stale-MDM-image finding with a
   fully independent evidence chain. See
   [`gate1-gate2-independent-reverification-2026-08-11.md`](../research/gate1-gate2-independent-reverification-2026-08-11.md).
2. ~~Resolve trigger provenance for the 90 executions whose input omitted a
   trigger identity; a direct API start alone does not identify the caller.~~
   **Done 2026-08-12.** All 92 executions in a freshly captured 30-day window
   (2 more than the draft's 90/114 split — expected drift, not a discrepancy)
   that omitted a `trigger` field resolve via CloudTrail `StartExecution`
   correlation to a single IAM identity, `admin-user`, calling
   `aws stepfunctions start-execution` from the CLI — not an unattributed gap.
   Same addendum as gate 1, second section.
3. ~~For each successful workflow class, bind at least one current-cohort
   execution to its expected durable output and actual consumer: S3 manifest,
   Snowflake inbox/load, dbt freshness, active graph pointer, dashboard object,
   reconciliation row, or operator artifact as applicable.~~
   **Done 2026-08-12.** Chain G bound end-to-end (execution → S3 manifest →
   `SNOWFLAKE_REFRESH_STATUS` row, matching row/table counts and timing) with
   a noted caveat that no execution has yet run under the very latest
   task-definition revision (deployed ~45 min before capture). Chain T bound
   the same way. Chain M confirmed live/non-stale but **not** individually
   bindable in Snowflake (no per-run tracking column exists on any MDM
   table — a real observability asymmetry vs. chain G/T, worth carrying into
   the portfolio-decision ticket). Chain I correctly has zero executions to
   bind (dormant, matches the draft). Chain R deferred to gate 4 by design.
   **Structural finding that supersedes the per-class results:** 2 confirmed
   Snowflake-landed artifacts (a `gold_refresh` and a `seed_universe` run)
   have **no corresponding Step Functions execution at all** — direct
   CLI/ECS invocations bypass the Step-Functions-scoped inventory this audit
   is built on entirely. Same addendum, third section.
4. ~~Audit the graph candidate/activation mismatch for the seven ordinary MDM
   composite paths and prove whether each candidate is activated, discarded,
   or currently orphaned.~~
   **Done 2026-08-12.** `GRAPH_GENERATION` has exactly 4 rows in the current
   schema's entire history (provisioned 2026-08-09) — audited exhaustively,
   not by sample. 1 `activated` (the schema's own bootstrap sync, unrelated
   to the seven paths), 1 `failed` (same bootstrap, first attempt), 2 stuck
   permanently in `building` with suspiciously round node/edge counts (100
   and 200) traced exactly to `MDM_GRAPH_LIMIT`'s default. Of those two: one
   (100/100) is from the **standalone** `mdm_sync_graph` utility (MDM E2E
   driver), not a composite path; the other (200/200) is the one confirmed
   instance of a composite path (`load_history`) reaching `sync-graph` —
   inside a run that ultimately `FAILED`. The other six composite paths
   (`bootstrap`, `mdm_gold`, `ownership_mdm_gold`, `silver_mdm_gold`,
   `bronze_seed_silver_gold`, `daily_incremental`) have **not succeeded even
   once** since the current graph schema was provisioned, so they've
   produced no candidate at all — not a graph-specific gap, a
   nothing-has-succeeded-post-cutover gap. Same addendum, fourth section.
5. ~~Confirm that terminal `SUCCEEDED` histories did not mask a required-stage
   failure through `Catch`, partial output, stale-generation verification, or
   non-fatal publication behavior.~~
   **Done 2026-08-12 — confirmed a real masking mechanism, not a clean bill
   of health.** Five machines (`bootstrap`, `bronze-seed-silver-gold`,
   `daily-incremental`, `load-history`, `silver-mdm-gold`) share an
   `MdmVerify` state with `Catch: States.ALL, ResultPath: null → GoldRefresh`
   — deliberate ("verify-graph must never block gold-refresh," per an inline
   comment), but erases all trace of the failure. Confirmed **live in
   production, 3 times**: `MdmVerify` failed all 4 allowed attempts
   (retries exhausted) in `bootstrap-ticket03-verify-1785426021`,
   `daily-incremental-ticket89-unblocked-1785856213`, and
   `daily-incremental-ticket74-repair-verify-1785752569`, each still
   reporting overall `SUCCEEDED`. All 3 predate the current graph schema
   (2026-08-09), so likely a cutover-transitional cause rather than an
   active ongoing failure — but the mechanism is unchanged today and would
   mask a real failure identically. The "strict" `bronze_seed_silver_gold`
   branch has no such Catch (fails closed). Non-fatal graph-review-publish
   behavior separately confirmed but narrower and explicitly documented.
   Partial output and stale-generation verification: checked, not found in
   available data. Same addendum, fifth section.
6. ~~Review the nine zero-execution workflows and every inferred or unknown
   consumer with the operator before passing facts to the portfolio-decision
   ticket.~~
   **Done 2026-08-12.** Consolidated gates 1-5 plus the draft's two open
   lists into a findings package (reconciled zero-execution list: 8, not 9
   — 2 deleted, 1 new; inferred/unknown consumer table cross-referenced
   against gates 1-5) and reviewed it live with the operator. Four decisions
   recorded: deregister the 7 orphaned MDM machines; accept the
   Step-Functions-bypass path as an intentional escape hatch; add
   visibility to `MdmVerify`'s non-blocking `Catch` without making it
   blocking; and default the 8 zero-execution workflows to **retirement
   candidates**, not assumed-intentional utilities. Two questions remain
   open for Ticket 14 itself: `residual_holds_graph`'s candidate-activation
   binding, and `generation_build`'s planned-vs-abandoned status. Same
   addendum, "Operator decisions" subsection.

## Answer

All six audit gates independently re-verified and resolved 2026-08-11 through
2026-08-12 — see
[`gate1-gate2-independent-reverification-2026-08-11.md`](../research/gate1-gate2-independent-reverification-2026-08-11.md)
for the full evidence chain. The draft's core facts held up under independent
re-derivation, with several findings sharpened or corrected along the way:
the zero-execution count is now 8 (not 9, for explainable reasons), the
graph-candidate gap is narrower and better-explained than "no proven active
consumer" implied (gate 4), a real failure-masking mechanism was confirmed
firing in production (gate 5, not previously known), and a structural gap
was surfaced that the original scope didn't anticipate: at least 2 real
production writes bypass Step Functions entirely, meaning this whole
inventory — and by extension gates 1-5 — is not a complete picture of what
produces durable output in this account.

Facts and the operator's four portfolio-lens decisions (see gate 6) are
ready for [Ticket 14 — Decide the Production Workflow Portfolio](14-decide-the-production-workflow-portfolio.md).
