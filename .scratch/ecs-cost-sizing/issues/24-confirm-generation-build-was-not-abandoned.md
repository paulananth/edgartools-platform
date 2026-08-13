# Confirm `generation_build` Was Not Abandoned

Type: task
Status: resolved
Blocked by: none

## Question

Was `generation_build` deliberately left dormant after its one-ever
execution (2026-07-22, per Ticket 12/13), or is its near-total absence of
use (21 days, zero repeats) evidence of an abandoned capability nobody
noticed had gone quiet?

Raised by [Decide the Production Workflow Portfolio](14-decide-the-production-workflow-portfolio.md),
which decided to keep this workflow on capability grounds — it is the only
machine in the portfolio that can produce a new graph generation at all,
and retiring it on a zero-recent-execution technicality would be an
accidental capability loss. That reasoning is sound regardless of the
answer here, but an owner's explicit confirmation is still needed before
this is treated as fully settled, and before
[Decide the Loop, Batch, and Concurrency Policy](15-decide-loop-batch-and-concurrency-policy.md)'s
deferred `BuildPartitions` `MaxConcurrency` sizing work is worth doing in
earnest.

## Answer

**Not abandoned — genuinely rare-by-design, confirmed from three
independent angles that all converge.**

**1. Design intent, from the module's own docstring**
(`edgar_warehouse/mdm/generation.py`): *"Each partition's content address
(kind, type, shard, MDM watermark, rule/schema version, input fingerprint)
determines whether a prior generation's built output can be reused instead
of rebuilt."* This is a content-addressed-reuse system by design — a new
generation is only meaningfully different from the last when the
underlying MDM watermark or rule/schema version has moved. It is not
built on any fixed cadence, and running it more often than that would
produce a reused, not rebuilt, output.

**2. The one trigger condition has never fired.** `rule_version`/
`schema_version` default to `"v1"` (`--mdm-graph-rule-version`/
`--mdm-graph-schema-version`, `deploy-aws-application.sh`) — traced via
`git log -S` to their introduction in commit `60514137` ("fix-pipelines:
Phase 7 Plans 07-01–07-05... generation builder, verified single-
generation activation") and **unchanged since**. No commit has ever
bumped either version. Combined with finding 1: the specific condition
that would warrant a second generation build simply hasn't occurred yet —
zero repeats is the expected outcome of that fact, not evidence nobody
noticed.

**3. Deliberate, recent engineering attention — not neglect.** As
recently as 2026-08-10 (well after the 2026-07-22 execution, and this
finding predates this ticket by 3 days), a completely separate
consolidation effort ([state-machine-consolidation](../../state-machine-consolidation/map.md)'s
ticket 02) explicitly reasoned about this exact machine and **deliberately
excluded it** from a broader MDM-machine consolidation pass: *"`generation_build`
was miscategorized as one of the '8 standalone single-stage MDM machines'
in this ticket's original text — it's actually a bespoke partition-plan/
fan-out-build/fan-in-verify/activate pipeline (its own Distributed Map),
structurally closer to the composed-5 than to a single-command wrapper. No
sibling machine shares its shape, so there's nothing to deduplicate —
excluded entirely."* Someone was actively thinking about this machine's
correct shape two weeks ago and chose to preserve it standalone — the
opposite of forgotten.

**Additional context, not itself the answer:** routine graph freshness is
served by a separate, regularly-run mechanism (`mdm sync-graph`, part of
the composed-5 pipeline machines and the consolidated `mdm_utility`
machine) — so the graph itself hasn't been stale or neglected for 21
days, only this specific "build an entirely new generation" capability
hasn't been needed, which is exactly what findings 1 and 2 predict.

**Decision confirmed: keep**, fully settling the capability-grounds
reasoning Ticket 14 already gave. This unblocks
[Ticket 15](15-decide-loop-batch-and-concurrency-policy.md)'s deferred
`BuildPartitions` `MaxConcurrency` sizing work to be pursued in earnest
whenever a real canary is warranted — not urgently, since nothing suggests
this machine will run again soon, but no longer blocked on "is this even
still wanted."
