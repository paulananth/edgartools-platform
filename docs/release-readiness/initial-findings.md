# Current-Head Production Launch Readiness: Initial Findings

**Captured:** 2026-07-14  
**Branch:** `codex/release-readiness`  
**Evidence mode:** Read-only and secret-safe. No production execution, deployment, or data mutation was started.

## Destination Boundary

This effort will find a decision-complete route to production operator readiness for an identified current release candidate. It covers the AWS workflows, Snowflake/dbt, MDM and hosted graph, read-only dashboard, monitoring, recovery, and signed evidence needed by operators.

Public or customer-facing launch readiness is a separate destination and is out of scope.

## Historical Go-Live Baseline

The `go-live` workstream records v1.6 as shipped with a Release Owner `GO` decision dated 2026-06-26 UTC. That decision is a historical baseline, not proof that the current code is ready to deploy.

The historical record has planning-integrity inconsistencies:

- The roadmap says all 12 v1.6 requirements are complete, while `REQUIREMENTS.md` still marks them pending.
- GSD artifact discovery reports 9 of 10 discovered plans summarized because Phase 8 lacks a conventional `08-02-SUMMARY.md` and Phase 10 has evidence without conventional plan/summary artifacts.
- Phase 8 evidence ends with a human checkpoint described as the remaining gate, while the roadmap and final decision packet later treat Phase 8 as complete.
- The final packet accepts GRAPH-04 on an evidence basis that did not include a committed Step Functions/CloudWatch record for the historical MaxConcurrency=4 execution.

These are evidence-maintenance concerns. They do not reverse the signed historical decision, but they prevent treating the old planning percentage as current-release proof.

## Live MaxConcurrency=4 Findings

Read-only AWS inspection found the current production `bronze_seed_silver_gold` state machine configured with a Distributed Map `BatchSilver` state at `MaxConcurrency=4`.

### Latest completed BatchSilver map inspected

Execution `bronze-seed-silver-gold-1783263883`, run on 2026-07-05:

- The execution-specific state-machine definition used `MaxConcurrency=4`.
- `BatchSilver` completed 603 of 603 map executions successfully.
- Failed, timed-out, and aborted map executions were all zero.
- The exact BatchSilver CloudWatch window contained zero `sec_pull_started` events.
- The same window contained zero `filing_artifact_pipeline_started` events.
- Searches found no `database is locked`, `DuckDB error`, lower/upper-case lock, partial, duplicate, or corruption indicators.
- The `shard_manifest_missing_monolith_fallback` event appeared 500 times, so the run exercised the write-contention risk path rather than avoiding it.
- CloudWatch recorded 501 `bronze_silver_completed` events and 502 `silver_publish_completed` events. Map success proves child workflow completion; the difference from 603 map items still needs a semantic explanation before event counts are used as data-completeness proof.
- `MdmRun` and `MdmBackfill` succeeded after `BatchSilver`.
- The overall workflow failed later at `MdmExport` after four failed task attempts.

### Other visible production executions

- Execution `bronze-seed-silver-gold-1783228247` also completed 603 of 603 BatchSilver map executions at MaxConcurrency=4, with no map failures or lock indicators, but emitted 3,175 `sec_pull_started` events. It therefore fails the no-SEC-refetch gate.
- Execution `bronze-seed-silver-gold-1783227045` was aborted shortly after BatchSilver began; 4 items were aborted and 599 remained pending. It is not validation evidence.
- Historical execution `bronze-seed-silver-gold-1782384165` was not discoverable from the current production state machine or by its direct historical identifier.

## Current Disposition

**BatchSilver concurrency:** Qualified PASS. A production run exercised MaxConcurrency=4 across 603 successful map items, including 500 monolith-fallback events, with no observed contention errors and no SEC refetch.

**Data uniqueness/completeness:** Not yet proven. Absence of duplicate or partial indicators in logs is not a table-level uniqueness or completeness check.

**End-to-end workflow:** FAIL for the inspected release because the workflow stopped at `MdmExport`. The BatchSilver result must not be presented as full-chain launch readiness.

## Decisions This Makes Visible

- What immutable commit and image digests constitute the release candidate?
- What evidence contract distinguishes a BatchSilver concurrency PASS from a full workflow PASS?
- What table-level checks prove that MaxConcurrency=4 produced neither duplicate nor partial filing data?
- What is the disposition of the downstream `MdmExport` failure before release?
- Which historical go-live artifacts should be reconciled versus replaced by a fresh current-release evidence packet?
- Which production data-completeness conditions, including hosted-graph population, are launch gates versus post-launch operations?
