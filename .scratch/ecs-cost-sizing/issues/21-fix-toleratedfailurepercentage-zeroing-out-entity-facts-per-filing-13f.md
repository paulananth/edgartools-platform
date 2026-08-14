# Fix `ToleratedFailurePercentage: 0` Zeroing Out Entity-Facts/Per-Filing/13F Coverage

Type: grilling
Status: resolved
Blocked by: none
Related: 20 (root cause of the window-1 failure that exposed this), 07
(broader Step-Functions-wide concurrency/failure-control standardization —
this ticket is a narrow, urgent slice of that same question, resolved ahead
of 07 because it's actively losing production data on every `load_history`
run, not just a design-consistency gap)

## Question

`load_history`'s `FetchEntityFacts`/`FetchPerFilingFundamentals`/
`FetchThirteenFHoldings` Distributed Maps (`deploy-aws-application.sh`,
`fundamentals_entity_facts`/`fundamentals_per_filing`/`fundamentals_thirteenf`)
each run `MaxConcurrency: 1`, `ToleratedFailurePercentage: 0` over N windows
covering the full CIK universe (currently ~52 windows at the widened
`window_size=1000`). Should tolerance be raised, should failure handling move
inside the per-window `ItemProcessor` instead, or both?

## Evidence — live incident, `ticket42-task35-fulluniverse-retry7`, 2026-08-14

Confirmed via `describe-map-run` on all three Maps in this execution
(`itemCounts`, identical shape on each): `total: 53`, `failed: 1`,
`aborted: 1`, `succeeded: 0`, **`pending: 51`**. Window 1 exhausted its 3
OOM retries (ticket 20's root cause, pre-fix `medium` profile); the Map then
aborted immediately — Step Functions Distributed Map behavior at
`ToleratedFailurePercentage: 0` is to stop launching new child executions the
moment cumulative failures exceed the threshold, which one failure does
instantly at 0%. Windows 2–53 (98% of the CIK universe) were never even
attempted, not just "not yet reached."

Confirmed live in Snowflake against the full 51,888-company universe
(`EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.COMPANY`):

| Table | Distinct CIKs | Coverage |
|---|---|---|
| `SEC_FINANCIAL_FACT` (entity-facts) | 21 | 0.04% |
| `SEC_FINANCIAL_DERIVED` | 21 | 0.04% |
| `ACCOUNTING_FLAG` | 0 | 0% |
| `EARNINGS_RELEASE` (per-filing, 8-K) | 34 | 0.07% |
| `EXECUTIVE_RECORD` (per-filing, DEF 14A) | 903 | 1.7% |
| `SEC_THIRTEENF_HOLDING` | 8,783 | 16.9% |

These small counts are residue from windows that happened to complete in
*earlier* `load_history` attempts (retry1–6), not from retry7 — retry7 added
zero net new coverage to any of the three tables, despite running for ~16
hours and reporting `SUCCEEDED` overall (the outer AD-13 `Catch` on each Map
correctly prevented a hard pipeline abort, but that same Catch is what let a
zero-progress run report success).

The `AD-13` design comment on these Maps states the intended failure mode:
*"Gaps self-heal via idempotent backfill; a hard abort would defeat that."*
That comment is correct about the **outer** Catch (Map failure doesn't block
MDM/gold) but the **inner** `ToleratedFailurePercentage: 0` contradicts its
own stated assumption — it doesn't produce "gaps," it produces "everything
but the one window that happened to run first," every single time any window
fails for any reason (OOM, transient SEC 5xx, a timeout), not just OOM.

## Answer

**Two changes, both scoped now; only the first is quick enough to land
before the next `load_history` run without a design debate:**

**1. Immediate stopgap — raise `ToleratedFailurePercentage`, don't leave it
at 0.** Recommend `15` (roughly 8 of 52 windows at the current window size).
Rationale: high enough that an isolated bad window (a genuinely huge filer,
a transient SEC 5xx, an EDGAR pagination timeout) doesn't blank out the rest
of the universe; low enough that a *systemic* break (bad image, bad
credential, schema migration not yet applied) still hard-stops the Map well
before it burns `large`-profile compute attempting all 52 windows doomed to
fail identically — protects the "spend less on AWS" goal ticket 22 is
scoping, not just correctness. Apply to all three Maps
(`fundamentals_entity_facts`, `fundamentals_per_filing`,
`fundamentals_thirteenf` in `deploy-aws-application.sz.sh`) — they share the
identical topology and risk profile (ticket 20's live evidence already
showed the OOM applied to entity-facts *and* per-filing identically). Use
the percentage form, not `ToleratedFailureCount`, so it keeps scaling
automatically if `window_size` (already widened once this session, 500→1000)
changes again.

**2. Structural fix — move failure handling inside the `ItemProcessor`,
so a window's exhausted retries never counts against the Map's tolerance at
all.** Wrap each `RunFundamentals*` per-window ECS task state with its own
`Catch` (`ErrorEquals: States.ALL`) that logs the failed
`{window_offset, window_limit}` pair (e.g. to a
`fundamentals_window_failed` structured log event, mirroring the existing
`mdm_relationship_skip`-style pattern already used elsewhere in this
codebase for "gap, not error" signals) and completes the child execution
successfully instead of letting it propagate as a Map-level failure. This is
the fix that actually matches the AD-13 comment's stated intent — every
window gets attempted regardless of any other window's outcome, with no
tolerance number to tune or get wrong, and genuinely isolated per-window
gaps (not "50+ windows silently skipped") become the norm. Rejected as the
*sole* fix for right now: real implementation + test surface (new Catch
target state per Map, a way to assert on it in
`test_load_history_state_machine.py`, and — importantly — something making a
high per-window failure rate visible, since a Catch-and-continue design
means Step Functions execution status alone can no longer be trusted to
reveal a "silently zero-progress run" the way this investigation just did
manually) large enough to warrant its own implementation pass rather than
bundling into the stopgap.

**Sequencing:** land #1 before the next full `load_history` run (one-line
change per Map, no new states/tests beyond updating the existing
`ToleratedFailurePercentage: 0` assertions in
`tests/architecture/test_load_history_state_machine.py`, if any target these
three Maps specifically). Treat #2 as its own follow-up ticket once #1 is
live and the immediate data gap is no longer actively growing with every
run — not blocking, but also not indefinitely deferred, since #1 alone still
has the "silent zero-progress success" failure mode if something systemic
breaks below the 15% threshold's ability to catch it (e.g. exactly 7 of 52
windows failing for unrelated reasons would still report `SUCCEEDED` with
~87% coverage silently missing).

**Not yet implemented** — this ticket is diagnosis + decision only, per this
map's planning-only Notes. Awaiting go-ahead to implement #1 (and to open
the #2 follow-up ticket).
