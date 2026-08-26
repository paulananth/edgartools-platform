# Decide the cross-stage coordinator and composite watermark contract

Type: grilling
Status: resolved
Blocked by: 05, 06, 07, 08

## Question

What coordination contract lets silver, MDM, gold, and graph publish
independently yet exposes a Change Propagation Run as agent-grade only when all
affected stages are complete and aligned?

Decide the stage state machine, ownership of expected-producer and outcome
records, event/outbox handoffs, monotonic source-key ordering, timeouts,
retry/DLQ/manual-repair states, stage-local rollback, and composite Decision
Watermark commit. The answer should determine whether the physical topology is
one coordinator or several independently triggered machines while preserving
the already-settled SNS/SQS and on-demand compute decisions.

## Answer

Grilled 2026-08-26, the last ticket in this session's chain (04-09). The
biggest finding came first: **the composite Decision Watermark this
ticket asks to design already exists**, at the validation-logic layer —
`edgar_warehouse/serving/decision_contract.py`'s `DecisionWatermark`/
`evaluate_agent_grade` (its own docstring cites "ticket 09 / ADR 0001" —
a *different* map's own local numbering, confirmed by cross-referencing
`docs/adr/0001-agent-decision-surface-first.md`, not a collision worth
worrying about). Real callers already exist in the Agent Decision Surface
read path (`subject_bundle_read.py` and siblings). This ticket's actual
job turned out to be: confirm that module is authoritative (it is — Q1),
reconcile the granularity mismatch between it and everything Tickets
04-08 built (below), and decide the topology and mechanism for feeding it
real data instead of the placeholder-ridden SQL sketch CLAUDE.md already
documents as broken.

**Granularity reconciliation:** the existing watermark is keyed by
`business_date` (one per platform-day); everything Tickets 04-08 decided
is keyed by `cause_reference` (one per source-family discovery
invocation, much finer-grained). Decided: the fine-grained signals feed
the coarse one — `business_date`'s components become true only once
*every* `cause_reference`-scoped Run touching that date has its own
per-stage completion barrier satisfied. This is the only reading
consistent with "fail-closed if anything is missing" meaning something
real, rather than a business-date-level rubber stamp sitting on top of
possibly-incomplete finer-grained work.

**No new MDM field on the watermark, confirmed deliberate:**
`REQUIRED_COMPONENTS` has no explicit `mdm_completeness_ok` — `graph_parity_ok`
already transitively proves MDM's state is correctly reflected (per
CONTEXT.md's `Per-Type Exact Relationship Parity`: MDM's eligible edge set
and the active hosted-graph edge set must have equal counts), provided
graph sync/verify ran against current MDM state. Documenting this as an
existing, correct design decision rather than adding a redundant field
that could theoretically disagree with parity.

**Topology: an aggregator, not an orchestrator.** Several independently-triggered
machines, unchanged (Ticket 03 already decided silver/MDM/gold/graph
publish independently) — plus one new, separate, lightweight reconciler
that only *watches* each stage's already-existing completion signal and
computes readiness. It never drives or sequences the stages themselves; a
heavy single coordinator would re-couple exactly what Ticket 03 decided to
decouple. **Scheduled, not event-driven** — matches this repo's general
preference for idempotent scheduled sweeps over fragile event chains, and
avoids adding the aggregator as a new dependency any individual stage's
own completion path has to remember to call.

**What the aggregator does, concretely:** reads each stage's Postgres-tracked
outcome directly (silver's completion barrier — Ticket 35; MDM's
publication-outbox lifecycle state — Ticket 36), makes one lightweight
Snowflake query per `cause_reference` for gold's native refresh version
(Ticket 39) and graph's parity/generation status (Ticket 40), and writes
one composite row per `cause_reference` recording alignment. A separate
daily rollup derives the `business_date`-level values and calls
`evaluate_agent_grade` with them.

**Stage state machine, expected-producer/outcome ownership, monotonic
source-key ordering: not new decisions.** Each stage already owns its own
lifecycle and outcome records independently (Tickets 05/06/07/08); the
aggregator introduces no new unified state machine and enforces no new
ordering — per-key ordering is already handled within each stage
(Tickets 18/19 for silver, Ticket 06's confirmed-already-working order
dependencies for MDM).

**Timeouts:** a watchdog SLO for cross-stage alignment specifically,
reusing `publication.py`'s already-built and tested 5-minute-warning/
15-minute-hard-alert pattern rather than inventing a new one.

**Retry/DLQ/manual-repair states: none new on the aggregator.** It's
observe-only (matches Q7's stage-local-rollback answer below) — a stuck
`cause_reference` is, by construction, stuck because exactly one stage
hasn't completed. The watchdog alert names *which* stage (readable
directly off the aggregator's own per-stage join); an operator repairs it
through that stage's own existing mechanism (Ticket 25's conflict/repair,
`stewardship.py`'s quarantine review, a graph generation retry). A second,
aggregator-owned repair path would duplicate machinery that already
exists per stage.

**Stage-local rollback:** purely observed, never orchestrated. Every
stage already owns independent rollback/repair; the aggregator just
reflects "not yet aligned" until a stage's own repair completes and
re-reports success on its own.

**SNS/SQS preservation:** confirmed, no interaction needed. The aggregator
reads post-hoc completion state from each stage's own store — it has no
reason to see individual SEC fetch/SNS/SQS events, and doesn't touch the
decoupled-bronze-pipeline architecture at all.

Concrete build (the scheduled job, the composite table, the daily rollup,
and fixing the two known SQL gaps in the existing Decision Contract
sketch) deferred to new [Ticket 41](41-build-cross-stage-watermark-aggregator.md),
blocked on Tickets 35/36/39/40 (each stage's own completion-evidence
mechanism) actually existing first.
