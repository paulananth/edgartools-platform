# Spec: Wire `fetch-adv-bulk` into `load_history` and `daily_incremental`

**Status:** ready-for-agent
**Type:** spec
**Date:** 2026-07-28
**Repo:** edgartools-platform
**Related:** [ADV Pipeline map](../adv-pipeline/map.md) · [06 — Automated Fetch and Pipeline Wiring Shape](../adv-pipeline/issues/06-automated-fetch-and-pipeline-wiring.md)

## Problem Statement

The `fetch-adv-bulk` CLI subcommand (which fetches new SEC/IAPD `advFilingData` monthly
archives and stages a source manifest) is fully implemented and tested, but nothing ever
calls it in production. Today, keeping ADV adviser/fund silver data current requires an
operator to run `fetch-adv-bulk` and `ingest-relationship-sources` by hand for every
company universe load and every day's incremental refresh. The platform's operator (who
runs `load_history` for new company universes and relies on `daily_incremental`'s
scheduled daily run for ongoing refresh) has no way to get current ADV data without a
manual, easy-to-forget extra step outside the pipeline that already handles every other
SEC data source automatically.

## Solution

Wire `fetch-adv-bulk` (followed by `ingest-relationship-sources`, its existing separate
manifest-consuming step) into both `load_history` and `daily_incremental` as a new
sequential Step Functions Stage, placed after bronze/silver capture and before MDM entity
resolution — so `mdm run`/`mdm derive-relationships` always sees the freshest ADV silver
data available in the same execution, with zero new operator action required. This closes
out decisions 2–4 of the ADV Pipeline map's ticket 06 ("Automated Fetch and Pipeline
Wiring Shape"), whose decision 1 (the `fetch-adv-bulk` command itself) already shipped.

## User Stories

1. As the platform operator running `load_history` to onboard a new batch of companies, I
   want ADV adviser/fund data fetched and ingested automatically as part of the same
   execution, so that MDM entity resolution and graph sync for the new universe include
   current adviser/fund relationships without a manual follow-up step.
2. As the platform operator relying on `daily_incremental`'s scheduled daily run, I want
   ADV data refreshed automatically once a new monthly `advFilingData` archive is
   published, so that the platform's adviser/fund data doesn't silently go stale between
   `load_history` runs.
3. As the platform operator, I want the ~29 days/month where no new ADV archive has been
   published to cost nothing extra in `daily_incremental`'s runtime, so that daily
   incremental doesn't grow slower or burn more compute for a source that only changes
   monthly.
4. As the platform operator performing a manual ADV repair (e.g., re-ingesting a period
   that failed to parse correctly), I want to pass `dataset_period` and `force` as Step
   Functions execution input, so that I can target a specific month without editing code
   or falling back to a fully manual CLI invocation.
5. As the platform operator, I want a transient ADV fetch/ingest failure to never abort
   the rest of `load_history` or `daily_incremental`, so that ownership, fundamentals,
   and Company Identity data (whose entity resolution ticket 02's map-level requirement
   says must never be gated on ADV/private-fund-detail fidelity) continue to reach MDM and
   the graph even if the ADV source has a bad day.
6. As a future engineer reading the generated Step Functions JSON, I want the new stage's
   shape validated by the same structural test harness that already covers
   `load_history`/`daily_incremental`, so that a change here is caught by CI the same way
   every other stage's shape already is.

## Implementation Decisions

- **New sequential Stage, not a parallel Map.** `fetch-adv-bulk` fetches a handful of
  sequential monthly archives (13 for a baseline load, not CIK-windowed), so it does not
  fit the existing per-window Distributed Map pattern used for CIK-scoped work
  (`WindowedBootstrap`, `Stage0CompanyIdentity`, etc.). It is a single ECS task step, the
  same execution pattern already used for `GoldRefresh` and `Stage0CompanyIdentity`'s
  precedent stage.
- **Placement:** in `load_history`, the new stage runs after `Stage1BThirteenF` (the last
  bronze/silver step) and before `MdmRun`. In `daily_incremental`, it runs after
  `RunWarehouseTask` and before `MdmRun`. In both cases this mirrors the existing
  `Stage0CompanyIdentity` precedent of inserting a new named stage ahead of the
  once-per-execution MDM/gold chain, so `mdm run --entity-type all` (which already covers
  advisers/funds as part of its full sweep) and `mdm derive-relationships` see fresh ADV
  silver in the same execution — no separate `--entity-type adviser`/`fund` call needed.
- **The stage is a two-task pair, not one task:** `FetchAdvBulk` (runs `fetch-adv-bulk`)
  followed by `IngestAdvBulkSources` (runs `ingest-relationship-sources
  --source-manifest <path>`), preserving the already-decided separation between fetching
  (producing a reviewable manifest as evidence) and ingesting (consuming it into silver).
  The manifest path handed to `ingest-relationship-sources` is derived the same way
  `Stage0CompanyIdentity`'s per-window steps re-derive `cik_windows.jsonl`'s S3 key
  independently via `States.Format` and `$$.Execution.Name` — both commands compute the
  same deterministic, run-id-scoped manifest path from the existing manifest-path
  convention (command name + run id), rather than the state machine capturing and passing
  along `FetchAdvBulk`'s literal output.
- **`--force` requires Choice-based branching, not a single `States.Format` command
  array.** Unlike `artifact_policy` (an existing SM-input field that's always a *value*,
  interpolated directly into the command string), `fetch-adv-bulk`'s `--force` is a
  bare boolean CLI flag with no value — it must be present or absent as a whole token, which
  `States.Format` string interpolation cannot conditionally do within one command array.
  The new `ForceCheck` Choice state routes execution to one of two literal `FetchAdvBulk`
  Task definitions — one whose command array includes the literal `--force` token, one
  that omits it — both converging on the same next state. `dataset_period` has no such
  problem: it is passed as `--dataset-period <value>`, always present, mirroring
  `ArtifactPolicyCheck`/`ArtifactPolicyDefault`'s existing Check→Default pattern, with an
  empty-string default. (The `fetch-adv-bulk` CLI dispatch already treats an empty
  `dataset_period` the same as an omitted one — this was intentionally built that way when
  `fetch-adv-bulk` shipped, specifically so the empty-string-default SM pattern would work
  without further CLI changes.)
- **SM-input Check/Default states**, mirroring `ArtifactPolicyCheck`/`ArtifactPolicyDefault`:
  - `DatasetPeriodCheck` → `DatasetPeriodDefault` (injects `""`) when `$.dataset_period` is
    absent, otherwise proceeds directly.
  - `ForceCheck` routes on `$.force`'s presence/value to the two `FetchAdvBulk` Task
    variants described above; no injected default state is needed since the Choice itself
    supplies the effective default (no `--force` token) via its `Default` branch.
  - Both fields are optional and unset by default — the normal `load_history`/
    `daily_incremental` path passes neither; they exist only for the manual repair case.
- **Lenient failure handling (`Catch`), matching the existing Branch B / AD-13 pattern**
  used by `Stage1BEntityFacts`/`Stage1BPerFiling`/`Stage1BThirteenF` and `MdmVerify`: a
  failure in `FetchAdvBulk` or `IngestAdvBulkSources` is caught and falls through to
  `MdmRun` rather than aborting the execution. This directly implements the ADV Pipeline
  map's standing requirement (ticket 02's Notes) that entity resolution and graph sync
  must never be gated on ADV/private-fund-detail fidelity.
- **`daily_incremental`'s existing daily schedule (`cron(0 12 * * ? *)`,
  `infra/terraform/accounts/prod/scheduled_daily_incremental.tf`) needs no changes.**
  Ticket 06 decision 3 ("daily invocation... no fixed day-of-month gate") is already
  satisfied by this existing schedule — `fetch-adv-bulk`'s own local-check-first logic
  (already implemented: `fetch_adv_bulk_sources` makes zero network calls when the current
  window is already fully ingested) is what makes the ~29 no-op days/month cheap, not a
  change to the schedule itself.
- **Both `write_load_history_definition` and `write_warehouse_mdm_gold_definition`
  (`infra/scripts/deploy-aws-application.sh`) need this change independently** — they are
  separate Python heredocs with no shared helper between them, matching how
  `Stage0CompanyIdentity` already had to be built twice (once per function) with an
  explicit "keep in sync" comment at each definition. The same convention applies here.

## Testing Decisions

- **Primary seam: the existing generated-JSON structural test harness**
  (`tests/architecture/test_load_history_state_machine.py` and
  `tests/architecture/test_daily_incremental_state_machine.py`). Both already extract the
  real bash function's source, execute it with dummy ARNs via a `bash` subprocess (no AWS
  calls), and assert on the resulting JSON's state names, `Next`/`Catch` wiring, and
  `Command` arrays. This is the highest existing seam and was purpose-built for exactly
  this kind of change (it already covers `Stage0CompanyIdentity`'s equivalent insertion).
  New tests, following the same naming and assertion style already used in both files:
  - the new stage runs after the bronze/silver stage and before `MdmRun` in both state
    machines;
  - the `FetchAdvBulk` Task's command shape is correct with no SM-input overrides (no
    `--dataset-period`/`--force` tokens beyond the empty-string default);
  - `DatasetPeriodCheck`/`DatasetPeriodDefault` precede the new stage, mirroring the
    existing `test_window_size_and_total_cik_limit_checks_precede_compute_windows`-style
    assertion;
  - `ForceCheck` routes to two distinct `FetchAdvBulk` command shapes (with and without
    the `--force` token);
  - `IngestAdvBulkSources`'s `--source-manifest` argument resolves to the same
    deterministic path `FetchAdvBulk` writes to;
  - a `Catch` on both new Task states falls through to `MdmRun`, mirroring
    `test_mdm_export_precedes_mdm_sync_graph`-style Catch assertions already used for
    `MdmVerify`.
  - `test_bootstrap_unaffected_by_daily_incremental_restructure`-style assertion:
    `bootstrap`'s state machine (which shares underlying helper code with
    `daily_incremental` but is architecturally separate) is unaffected by this change.
- **No changes needed to `tests/application/test_adv_bulk_fetch.py` or
  `tests/application/test_fetch_adv_bulk_command.py`** — this spec only wires an already-
  built and already-tested command into Step Functions; it does not change
  `fetch-adv-bulk`'s own behavior.
- **What makes a good test here:** assert on the generated JSON's structure and command
  shape (external, observable behavior of the deploy script), not on the Python
  heredoc's internal variable names — matching how every existing test in both files
  already operates purely on the parsed JSON output, never on the bash/Python source.

## Out of Scope

- Any change to `fetch-adv-bulk`'s own CLI flags, pure logic, or the manifest format it
  produces — that is already shipped and tested.
- The Firm Roster CSV completeness cross-check (ticket 08 on the ADV Pipeline map) — a
  separate, much larger piece of work, specified independently.
- Changing `daily_incremental`'s cron schedule or adding a new EventBridge rule — the
  existing daily schedule already satisfies this stage's cadence needs.
- Backfilling ADV data for executions that already ran before this change ships — this
  only affects future `load_history`/`daily_incremental` executions.
- Real deploy-time validation (`terraform plan`, an actual Step Functions execution
  against dev/prod) — covered by the existing manual smoke-test convention for Step
  Functions changes in this repo (deploy to dev, inspect one real execution), not by this
  spec's automated test seam.

## Further Notes

- This spec exists specifically because deferring this work was a deliberate, documented
  decision in an earlier session (ticket 06's Answer): editing
  `infra/scripts/deploy-aws-application.sh` was judged too risky to do blindly, without a
  way to validate against a real deploy dry-run in that session. Discovering that
  `tests/architecture/test_load_history_state_machine.py` /
  `test_daily_incremental_state_machine.py` already provide exactly that validation
  (network-free, structural, generated from the real bash function) substantially
  de-risks this work relative to how ticket 06 originally described it — an implementer
  should lean on that harness heavily, writing the new structural tests first before
  editing the Python heredocs (TDD at this seam is very natural here).
- `mdm run --entity-type all` already resolves adviser/fund entities as part of its full
  sweep (confirmed working, per the ADV Pipeline map's Notes) — this spec does not need a
  separate `--entity-type adviser --entity-type fund` call; the new stage only needs to
  guarantee fresh ADV *silver* data exists before the existing `MdmRun` state runs.
