Type: grilling
Status: open

## Question

Should the platform enforce mutual exclusion across *different* SEC-fetching
commands (`daily-incremental`, `bootstrap`, `bootstrap_full`,
`targeted_resync`, `bootstrap-batch` -- all five share
`_capture_submission_bronze_snapshot`, plus the separate artifact-fetch
loop in `bronze_filing_artifacts.py`), so that only one command's worth of
SEC request traffic runs at a time platform-wide?

## Why this is a real, separate decision

[Ticket 06](06-fix-cross-task-sec-rate-limit-compliance.md) fixes each
*command's own* internal concurrency to stay within SEC's 9-10 req/sec
ceiling (via ticket-03-style intra-task threading instead of cross-task
fan-out). But that only guarantees compliance if no *other* SEC-fetching
command is running at the same time. Confirmed via code reading:
`pipeline_run_lease` (`silver_store.py:2707`) is a generic, reusable
mutual-exclusion primitive (atomic acquire, staleness reclaim after a
configurable timeout), but the only lease name actually registered
anywhere in the codebase is `daily_identity_refresh`
(`warehouse_orchestrator.py:141`), used solely to guard `daily-incremental`'s
own identity-refresh-window computation against itself. There is currently
**no** lock preventing, for example, an operator-triggered `bootstrap-batch`
run from overlapping with a scheduled `daily-incremental` execution -- both
would be internally compliant after ticket 06's fix, but could jointly
exceed SEC's stated 10 req/sec per-operator ceiling.

## The real tradeoff

A shared "SEC fetch active" lease would serialize these commands
platform-wide -- correct for compliance, but a real operational cost: today
nothing stops (and nothing measures whether anyone actually relies on)
running e.g. a manual `targeted_resync` while `daily-incremental` is
mid-run. Serializing them could meaningfully lengthen wall-clock time for
whichever command has to wait, especially since `daily-incremental` alone
already takes ~3.5 hours end to end (per ticket 01's measurement).
Alternatives worth weighing: a hard mutual-exclusion lease (simplest,
correct, most conservative); a shared rate budget instead of full exclusion
(e.g. a distributed token bucket dividing the 9-10 req/sec ceiling across
whichever commands are concurrently active -- correct but real new
infrastructure to build and operate, the kind of complexity ticket 03
deliberately avoided by choosing intra-task threading over cross-task
coordination); or accepting the residual risk if concurrent runs are rare
enough in practice to be an acceptable compliance exposure (needs real
operational data on how often multiple SEC-fetching commands actually
overlap today -- not yet measured).

## Done when

A decision -- mutual exclusion, shared budget, accept the risk, or
something else -- with reasoning tied to real operational frequency data
where the decision depends on it (e.g. "accept the risk" requires knowing
how often overlap actually happens, not assuming it's rare).
