Status: ready-for-agent

Parent: [Ticket 04 — Audit load_history's internal large-profile states for the unscoped-load shape](../large-profile-unscoped-load-audit/issues/04-audit-load-history-internal-large-states.md), a child of the [Large-profile unscoped-load audit](../large-profile-unscoped-load-audit/map.md) wayfinder map.

## Problem Statement

Tonight, a live production Step Functions execution OOM-killed on the
`MdmRun` state because `GraphSyncEngine.prime_relationship_type` loaded an
entire shared relationship table (563,631 rows, ~2GB of ORM objects) into
memory before the code knew what subset it needed — an unscoped full load
of a shared table before scoping is known.

Ticket 04, as originally charted, listed six `load_history`-internal
`large`-profile states to audit for this shape. Investigating it (this
spec's own preparation) found the original list was built from an
approximate line-number inventory gathered while charting the parent map,
and was half wrong: `ReleaseSecFetchLease`, `ReduceIdentityRefresh`, and
one hardcoded `SeedUniverse` state actually live inside
`write_warehouse_mdm_gold_definition` — `bootstrap`/`daily_incremental`'s
own shared state-machine builder, exact scope of ticket 02 — not
`load_history`. Those moved to ticket 02's spec (addendum). What's left,
genuinely `load_history`-internal, is two: `ComputeWindows` (window
planning) and the 3 per-window fundamentals fetches (`fetch-entity-facts`,
`fetch-per-filing-fundamentals`, `fetch-thirteenf-holdings`, which share
one audit question since they're structurally similar per-window fetches).

`ComputeWindows`'s own code comment already documents a directly relevant,
pre-existing pattern: it "hydrated the full canonical silver.duckdb" and
separately calls `persist_run_manifest`, which "reads that same
~1GB+-and-growing canonical file fully into a Python bytes object for its
immutable reference snapshot." Whether this specific hydrate call already
went through the seed-universe-narrow-hydrate map's streaming fix (PR
#392, which fixed the *identical* full-canonical-hydrate pattern for
`seed-universe`) or is a separate, still-unbounded code path was never
confirmed — `ComputeWindows` is currently only protected by generous task
sizing (`large`, 8GB), the same "safe until it isn't" position MANAGES_FUND
was in before tonight.

A second, genuinely new finding surfaced during the same investigation and
is folded into this ticket rather than spun into a 5th: `silver_mdm_gold`
(the `BatchSilver` reprocessing pipeline's state-machine builder,
`write_silver_mdm_gold_definition` — covered by none of this map's other
tickets) has its own hardcoded `wh_large_arn` `SeedUniverse` state, with a
comment citing the same full-hydrate OOM history that justified
`load_history`'s own SeedUniverse hardcode — but that hardcode was already
fixed: task-profile-consolidation ticket 07 confirmed `load_history`'s
SeedUniverse now routes through `command_task_profile('seed-universe') ==
"medium"` (ticket 06's decision, after the streaming-hydrate root cause
was fixed). `silver_mdm_gold`'s copy was never revisited after that
decision landed, and (per ticket 02's addendum) neither was a third,
near-identical hardcode inside `write_warehouse_mdm_gold_definition`.

## Solution

Confirm whether `ComputeWindows`'s full-canonical hydrate shares the
already-fixed streaming path or is a separate, still-unscoped one; fix it
the same way MANAGES_FUND/INSTITUTIONAL_HOLDS were if it's the latter.
Check the 3 fundamentals-fetch commands for the same shape. Resolve the
`silver_mdm_gold` SeedUniverse hardcode by routing it through
`command_task_profile()`'s shared lookup (mirroring the exact,
already-proven pattern `load_history`'s own SeedUniverse fix used) unless
a genuine reason to diverge is found that ticket 06/07 didn't already rule
out — and confirm this ticket's answer stays consistent with whatever
ticket 02 resolves for its own, near-identical `SeedUniverse` hardcode.

## User Stories

1. As the platform operator, I want confirmation of whether
   `ComputeWindows`'s canonical-`silver.duckdb` hydrate call is the same
   function `seed-universe`'s streaming-hydrate fix (PR #392) already
   covers, or a separate, still-unbounded read path — a fact this ticket
   should establish by tracing the actual function call, not by assuming
   from the code comment's age.
2. As the platform operator, I want the same confirmed for
   `persist_run_manifest`'s "reads that same ~1GB+-and-growing canonical
   file fully into a Python bytes object" behavior — is this bounded
   anywhere today, or genuinely unscoped and just currently small enough
   not to have failed yet.
3. As the platform operator, I want real, current measurements (canonical
   `silver.duckdb`'s actual size today, growth trend if knowable) rather
   than the "1.5GiB, comfortably inside medium's envelope" figure task-
   profile-consolidation ticket 06 recorded for a *different* call
   site (seed-universe's own merge/publish step) — that number is not
   automatically this ticket's answer for `ComputeWindows`.
4. As the platform operator, I want each of the 3 per-window fundamentals
   fetches (`fetch-entity-facts`, `fetch-per-filing-fundamentals`,
   `fetch-thirteenf-holdings`) checked for whether their "per-window"
   framing is genuinely enforced by a bounded query, or whether any of
   them internally reads a broader dataset than the current window before
   filtering — the same question ticket 02 asks of
   `_run_submissions_bronze_then_silver`'s call sites, applied to these
   three commands' own internals.
5. As the platform operator, I want the `silver_mdm_gold` `SeedUniverse`
   hardcode routed through `command_task_profile('seed-universe')` the
   same way `load_history`'s own SeedUniverse already is, unless a
   concrete reason not to is found — not left on a stale justification
   that predates the actual fix.
6. As a future engineer, I want this ticket's `SeedUniverse` finding and
   ticket 02's near-identical one resolved with the same answer (both
   route through the shared lookup, or both have the same documented
   reason not to) — not two sessions independently reaching different
   conclusions about the same underlying question.
7. As a future engineer, I want a written record distinguishing "confirmed
   already safe" from "genuinely new gap, now fixed" for each of the four
   `load_history`-internal states plus the `silver_mdm_gold` finding, so
   nobody re-investigates ground this ticket already covered.
8. As a future engineer, I want any batch-scope fix built here (for
   `ComputeWindows` or a fundamentals fetch, if a real gap is confirmed)
   to follow the exact pattern already proven twice tonight — batch by a
   natural key, release each batch's state before the next, red-before-
   green regression test.
9. As the on-call operator, I want to know whether `ComputeWindows`'s
   hydrate pattern is already at meaningful risk today or has years of
   headroom at current growth rates, so I know whether to treat any
   finding here as urgent or routine.
10. As a future engineer, I want any genuinely new risk found outside the
    four named states and the `silver_mdm_gold` SeedUniverse finding to
    graduate into its own ticket on the parent map, per wayfinder's
    fog-of-war convention, rather than be folded into this one.

## Implementation Decisions

- **`ComputeWindows`/fundamentals fetches**: no single pre-existing seam
  covers all four the way tickets 01-03 each found one — these are four
  distinct CLI commands (`compute-windows`, `fetch-entity-facts`,
  `fetch-per-filing-fundamentals`, `fetch-thirteenf-holdings`), each
  implemented in its own module. Locate each command's handler during
  implementation (via `edgar_warehouse/cli.py`'s subparser wiring, the
  same way `mdm_entity_backfill.py`'s `run_mdm_entity_backfill_sweep` was
  found for ticket 02) and test at that command's own natural entry
  point — do not force a shared seam that doesn't exist.
- **`SeedUniverse` routing fix**: `write_silver_mdm_gold_definition`
  (`infra/scripts/deploy-aws-application.sh`) — an infra-script bash
  function. Test using the exact pattern
  `tests/architecture/test_seed_universe_task_profile_routing.py` already
  established for `load_history`'s own SeedUniverse: extract the
  function's source text, run it under a real bash subprocess with a
  stubbed `command_task_profile()`, and prove the stub's answer — not the
  hardcode — determines the resulting `TaskDefinition` ARN in the
  generated state-machine JSON. This is a direct template, not a
  from-scratch design.
- **Memory measurement method** (for `ComputeWindows`/fundamentals
  fetches, if the audit reaches actually measuring something): mirror
  tonight's MANAGES_FUND/INSTITUTIONAL_HOLDS investigation —
  `psutil.Process().memory_info().rss`, not `resource.getrusage()`
  (sticky high-water-mark, unit-inconsistent across platforms — a mistake
  this session already made and caught once).
- **If `ComputeWindows`'s hydrate is confirmed unscoped and genuinely at
  risk**: the fix pattern depends on what's actually being hydrated —
  if it's the same full-canonical-file read the seed-universe streaming
  fix already solved, the fix may be as simple as routing `ComputeWindows`
  through that same already-fixed code path rather than a separate,
  duplicated hydrate call. Confirm this before designing a new fix from
  scratch — reusing an existing fix is preferable to building a second,
  parallel one for the identical underlying read.
- **No changes to `load_history`'s or `silver_mdm_gold`'s Step Functions
  step ordering, retry/timeout configuration, or windowing strategy** are
  in scope, except the `SeedUniverse` task-profile routing change itself.

## Testing Decisions

- The `SeedUniverse` routing fix must be proven via the same
  routing-not-value-match discipline
  `test_seed_universe_task_profile_routing.py` already established — a
  test that only checks the final `TaskDefinition` ARN equals the medium
  ARN would pass even if the hardcode were left in place and happened to
  agree; the test must prove the *call* to `command_task_profile()`
  actually happens.
- If a genuine unscoped-load gap is confirmed in `ComputeWindows` or a
  fundamentals fetch and fixed, the regression test must be proven
  **red without the fix** first, following tonight's established
  discipline (a spy or count on batch/query calls, disjoint coverage
  across batches, full-universe coverage confirmed).
- If any of the four states or the `SeedUniverse` finding concludes no fix
  is needed, no new test is required — but the evidence checked (which
  function was traced, what it does, why it's safe) must be recorded in
  the ticket's resolution.
- Full `tests/architecture/`, `tests/unit/`, and `tests/mdm/` suites, plus
  the full repo suite, must stay green — matching tonight's baseline
  (2320 passed, 4 skipped, only the 2 pre-existing unrelated
  `test_bootstrap_dbt_snowflake_secret.py` failures documented in
  CLAUDE.md).

## Out of Scope

- The other 3 tickets on the Large-profile unscoped-load audit map
  (`residual_holds_graph`'s mdm-large steps, the core warehouse commands'
  audit — now including the 3 states moved there by addendum — and
  gold-refresh's streaming-fix completeness) — each is its own separate
  spec/session.
- Re-fixing anything already covered by task-profile-consolidation
  (tickets 01-07, all resolved) or seed-universe-narrow-hydrate — this
  spec only adds a check for whether their fixes' *scope* actually covers
  `ComputeWindows`/`silver_mdm_gold`, not a re-litigation of those fixes
  themselves.
- Any change to `load_history`'s or `silver_mdm_gold`'s task-profile
  sizing (the `large`/8GB reservation itself) — this ticket is about the
  Python-level load shape, not whether the current memory ceiling is
  correctly chosen.
- Deploying or restarting any production pipeline as a result of this
  work — build any fix and its tests; deployment is a separate, explicit
  follow-up decision.

## Further Notes

- This ticket's scope was corrected mid-preparation (see Problem
  Statement) — the parent map's ticket 04 file and ticket 02 file were
  both updated to reflect the corrected attribution before this spec was
  written, so the wayfinder tracker and this spec now agree.
- The `silver_mdm_gold` `SeedUniverse` finding and ticket 02's own
  near-identical finding (a third hardcoded `SeedUniverse` inside
  `write_warehouse_mdm_gold_definition`) should very likely resolve the
  same way. Whichever ticket is worked first should leave a clear enough
  resolution that the other can confirm consistency quickly rather than
  re-deriving the same routing decision independently.
- Per the parent map's Notes: if this investigation surfaces a genuinely
  new, differently-shaped risk elsewhere in `load_history` or
  `silver_mdm_gold` that this spec doesn't name, graduate it as a new
  ticket on the map rather than fold it in here, per wayfinder's
  fog-of-war convention.
