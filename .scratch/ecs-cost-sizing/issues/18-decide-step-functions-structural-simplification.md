# Decide Step Functions Structural Simplification

Type: grilling
Status: resolved
Blocked by: 11, 14, 15, 17

## Question

How should the retained state machines be standardized so repeated ECS task
states, MDM chains, profile selection, input defaults, Map configuration,
retry/catch behavior, output summaries, and revision pinning have one clear
contract without erasing workload-specific safety boundaries?

Decide where shared generation is appropriate, where separate state machines
remain valuable, whether any workflow can safely use a different Step
Functions execution type, and how dead or contradictory selection paths are
removed. Preserve immutable release references, bounded replay, state-level
failure visibility, and an operator-readable execution history.

## Answer

Picks up directly where Ticket 06 (single workload profile contract) and
Ticket 11's GoF architecture review left off — Ticket 06 already fixed
*which profile* gets selected; this ticket decides *how the state machine
itself* gets built. Four decisions:

**1. Extend Ticket 06's single-authority principle to state construction
itself.** Ticket 06 eliminated `workflow_profile()`/
`task_definition_for_mdm_workflow()` as competing profile-selection
authorities. Ticket 11's GoF review found a broader duplication underneath
that: **eight separate copies of the actual ECS-task-state-building code**
(retry policy, input defaults, output shape, each hand-rolled per
generator). **Decision: one shared task-state template/builder function,
used by every state machine generator**, rather than each of the ~13
retained machines carrying its own copy.

**2. Retry/Catch policy becomes a required, explicit parameter of that
template.** Ticket 14 found `residual_holds_graph` was missing the same
non-blocking `Catch` the other 5 `MdmVerify`-sharing machines have — a real
inconsistency a disciplined shared template prevents by construction,
since no generator can silently omit it. Same structural-enforcement-over-
per-generator-discipline reasoning Ticket 17 used for its missing-counter
rule.

**3. Execution type: Standard everywhere, settled outright.** Standard's
state-transition cost is already confirmed immaterial (~$0.06/month
portfolio-wide, Ticket 13); every bounded MDM utility that could
theoretically fit Express's 5-minute ceiling runs too rarely for Express's
per-request pricing to beat Standard's near-zero cost; and Standard's
90-day execution history is directly relied on by Ticket 11's
masked-failure investigation and Ticket 13's cost reconstruction —
switching anything to Express would break tooling this map already built.
No exceptions; no evidence anywhere in this portfolio points toward
Express.

**4. No further merging of retained state machines beyond shared
generation code.** Considered collapsing `bootstrap`/`daily_incremental`/
`load_history` into one parameterized machine. Rejected: Ticket 11 found
these differ meaningfully in trigger/schedule/scope (bootstrap =
recent-only, daily_incremental = recurring, load_history = full-universe
historical) — real operational distinctions an operator relies on when
choosing one, not just config knobs on a shared shape. Decision 1's
shared-generation-code answer already captures the maintenance-burden win
without collapsing those operationally meaningful choices into one
machine with confusing parameters.

**Out of this map's planning-only scope, per its own Notes**: building the
actual shared task-state template and migrating all ~13 retained machines
onto it is a real code change — a follow-up implementation effort, same
pattern as every other decision this map has produced. No new fog or
tickets surfaced by this resolution; all four sub-questions closed
cleanly.
