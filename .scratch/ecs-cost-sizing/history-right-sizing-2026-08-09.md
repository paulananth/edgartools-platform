# Historical ECS Right-Sizing Evidence — 2026-08-09

## Scope and method

Read-only CloudWatch Container Insights query for account `690839588395`,
region `us-east-1`, cluster `edgartools-prod-warehouse`.

- Window: `2026-07-10T00:00:00Z` through `2026-08-10T00:00:00Z`.
- Period: one hour.
- Metrics: `CpuUtilized` and `MemoryUtilized` by
  `TaskDefinitionFamily`.
- CPU values are ECS CPU units; memory values are MiB.
- A missing series means no observed execution in this window, not proof that
  the profile is safe to remove.

## Observed profile history

| Profile | Allocation | Metric points | Maximum observed | Maximum of allocation | Historical interpretation |
| --- | --- | ---: | --- | ---: | --- |
| warehouse-small | 0.5 vCPU / 1 GiB | 0 | no data | — | No evidence; retain as a candidate only for bounded work after an execution-level canary. |
| warehouse-medium | 1 vCPU / 4 GiB | 193 | CPU 1024; memory 3934 MiB | CPU 100%; memory 96% | At the CPU and memory boundary; do not downsize. |
| warehouse-large | 2 vCPU / 8 GiB | 101 | CPU 2002; memory 5972 MiB | CPU 98%; memory 73% | CPU-bound at peak; retain for gold/heavy warehouse stages. |
| mdm-small | 0.5 vCPU / 1 GiB | 22 | CPU 512; memory 166 MiB | CPU 100%; memory 16% | Memory has room, but CPU has saturated; keep for verification/lightweight work only. |
| mdm-medium | 1 vCPU / 4 GiB | 70 | CPU 918; memory 3318 MiB | CPU 90%; memory 81% | Near the safe upper bound in historical runs; retain as the default full MDM profile. |
| mdm-large | 2 vCPU / 8 GiB | 6 | CPU 529; memory 380 MiB | CPU 26%; memory 5% | Sparse and likely not representative of heavy residual-holds work; do not globally downgrade. |

## Right-sizing recommendation

Keep the six named profiles, but make their workload contract explicit:

1. `warehouse-small` — bounded fetch/lease or other explicitly tested low-
   volume work. It has no historical evidence in this window, so it must not
   become the default by inference.
2. `warehouse-medium` — ordinary seed/ingest/batch work. It is already close
   to both resource limits during observed executions.
3. `warehouse-large` — gold builds, bootstrap-heavy work, and other
   CPU-intensive stages. The 2-vCPU tier is justified by the historical CPU
   peak and the repository's documented gold-build memory floor.
4. `mdm-small` — verification and lightweight checks. Do not use it for full
   MDM execution merely because memory is low; CPU has saturated.
5. `mdm-medium` — ordinary `mdm run --entity-type all`, bounded backfill,
   export, and sync stages. Historical memory reached 3.2 GiB and CPU 90%.
6. `mdm-large` — residual-holds/security/person/relationship workloads only,
   subject to execution-level evidence. The sparse low utilization series is
   insufficient to remove the profile, especially given prior lower-memory
   OOM evidence.

## Decision boundary

This is a sizing recommendation, not an approval to alter production. Before
changing a Step Functions reference, require a workload-specific canary with
peak memory below the proposed allocation, no OOM or retry regression,
acceptable duration, and a measured cost comparison. Re-query the history
after Claude's explicit handoff because the current map intentionally does
not treat the pre-handoff inventory as final.
