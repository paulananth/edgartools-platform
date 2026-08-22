# 01 — Audit residual_holds_graph's mdm-large steps for the unscoped-load shape

Type: task
Status: open

## Question

`residual_holds_graph` (`infra/scripts/deploy-aws-application.sh`, ~line
5124) is the one confirmed-live production path that runs MDM relationship
derivation on `mdm-large` outside of `mdm run --entity-type all`. Audit
each of its 7 steps for the MANAGES_FUND-shape risk — an unscoped full
load of a shared table before the code knows what subset it needs — and
fix any genuine gap the same way MANAGES_FUND/INSTITUTIONAL_HOLDS were
fixed (batch-scope the prime, release each batch's cache,
red-before-green regression test).

Steps to check:
- `MdmSecurities` (`mdm run --entity-type security`) and `MdmPersons`
  (`mdm run --entity-type person`) — these call `MDMPipeline.run_securities`/
  `run_persons`, a *different* subsystem from relationship derivation
  (entity resolution, not `derive_relationships()`). Confirm whether the
  mdm-run-throughput map's bulk-prefetch/bounded-round-trip fix for these
  also happens to bound memory, or whether there's a separate unscoped-load
  risk here. If a gap surfaces, it may need to graduate as a new ticket
  rather than be folded into this one — use judgment once you see what's
  actually there.
- `MdmIsInsider`, `MdmHolds`, `MdmCompanyHolds` — standalone
  `mdm derive-relationships --relationship-type X` calls for IS_INSIDER,
  HOLDS, COMPANY_HOLDS. Live row counts measured 2026-08-21 (902, 395,
  3,148 respectively) are all tiny relative to MANAGES_FUND's 563,631 —
  re-verify these are still small before concluding no fix is needed; if
  any has grown materially, treat it the same as INSTITUTIONAL_HOLDS was
  (pre-emptive fix before it becomes a live incident, not after).
- `MdmInstitutionalHolds` — already fixed tonight
  (`_SELF_PRIMING_RELATIONSHIP_TYPES`, `_derive_institutional_holds_batch`,
  PR #435/#436). Confirm this step's actual invocation
  (`--target-per-type 50000`) is consistent with the batched fix and
  doesn't need any further adjustment specific to this call site.
- `mdm export` (both the mid-pipeline call and the one inside
  `wire_mdm_tail`) — a different writer entirely
  (`_build_snowflake_writer`/`_build_snowflake_mirror_writer` in
  `edgar_warehouse/mdm/export.py`/`cli.py`). Check whether it has any
  unscoped full-table read/write shape of its own — this has never been
  investigated for this specific risk.

## Blocked by

None — can start immediately.
