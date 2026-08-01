# Research findings: bound daily identity to companies, daily artifacts to exact index accessions

## Scope and evidence standard

This note records established read-only production, SEC, canonical ticket, and repository findings. It proposes implementation follow-ups but makes no code or AWS mutation.

## Production execution evidence

Read-only inspection of AWS production account `690839588395` on 2026-07-30 and 2026-07-31 found that execution `daily-incremental-ticket03-1785413694` was still running the old live state-machine definition, whose `StartAt` was `ComputeWindows`.

`Stage0CompanyIdentity` ran from 08:17:58 ET until 18:13:57 ET, a duration of 9 hours 56 minutes. PR #316's bounded daily code had merged, but that code was not deployed in this execution.

The production evidence was obtained with read-only AWS CLI calls:

- `aws stepfunctions list-executions`
- `aws stepfunctions get-execution-history`
- `aws stepfunctions describe-state-machine`
- `aws ecs describe-tasks`
- `aws logs get-log-events`
- `aws logs filter-log-events`

`RunWarehouseTask` began at 18:13:57 ET. In CloudWatch log stream `warehouse-large/edgar-warehouse/9cdc6464215b48809cf3b0fad5f405df`:

- Daily index `form.20260729.idx` yielded 3,082 active CIKs.
- Bronze processing took 1,065.6 seconds.
- Silver processing took 551.4 seconds.
- The run then emitted `filing_artifact_pipeline_started` with 148,524 candidates.
- At 1,500 processed candidates, it had made 1,077 network fetches and recorded 120 errors.
- The log showed repeated `PoolTimeout` events taking approximately 82–94 seconds each.

This execution therefore demonstrates two independent causes for a greater-than-six-hour daily run:

1. Company identity work scanned an excessively broad universe before the warehouse task began.
2. Filing artifact processing expanded into a 148,524-candidate historical workload, with substantial network fetching and repeated long `PoolTimeout` delays.

## Official SEC universe and daily-index evidence

The live official SEC ticker references were inspected directly:

- [`company_tickers.json`](https://www.sec.gov/files/company_tickers.json): 10,432 rows, 8,017 distinct CIKs, and 2,415 additional rows caused by issuers with multiple tickers.
- [`company_tickers_exchange.json`](https://www.sec.gov/files/company_tickers_exchange.json): 10,411 rows and 8,001 distinct CIKs.

The July 29 SEC master daily index contained 3,084 distinct filer CIKs. Only 84 of those CIKs intersected the SEC ticker CIK universe. Filtering the whole filing-ingestion path to ticker-present issuers would therefore discard 3,000 daily filers, including relevant Form 4 and Form 13F filers.

Ticker presence is an appropriate company-identity eligibility signal. It is not a valid eligibility gate for filing or relationship ingestion.

## Canonical local ticket evidence

The canonical root-cause ticket, [`.scratch/release-readiness/issues/40-root-cause-empty-ticker-reference-pipeline.md`](./40-root-cause-empty-ticker-reference-pipeline.md), records:

- Active tracked CIKs intersecting the current SEC ticker file: 2,576.
- Active tracked operating entities: 2,462.
- Active operating entities also matching the ticker file: 1,795.
- Active union of `(entity_type = operating)` or `(present in current SEC ticker snapshot)`: 3,243.

This union is the evidence-backed daily and backstop universe for company identity. It is approximately 3.2K entities, not the roughly 26K active tracked universe currently scanned by the old live definition.

## Repository findings

The repository behavior establishes why the two bounds must be implemented separately:

- `compute-windows` obtains CIKs through `db.get_tracked_ciks` using active/bootstrap tracking statuses and applies no entity-type filter.
- The merged bounded daily path filters impacted CIKs only against active tracking status.
- `_run_submissions_bronze_then_silver` expands every recent and pagination accession associated with the selected submissions.
- `_configured_parser_accessions` then includes ownership, ADV, proxy, 13F, Item 5.02, and Item 2.02 accessions.
- Only ownership and Item 5.02 receive the two-year filter.

Consequently, bounding impacted CIKs does not bind filing artifact work to the accessions present in the forced daily-index window. A modest daily CIK set can still expand into a very large historical accession workload.

## Required behavior

### Company identity

Daily company identity and its backstop should process active tracked entities satisfying:

```text
entity_type = operating
OR CIK is present in the current official SEC ticker snapshot
```

The runtime must emit the exact eligible count used for each execution. The expected current order of magnitude is approximately 3.2K, with 3,243 established by the canonical local snapshot; the implementation must not hard-code that count.

The company-identity eligibility contract must be kept separate from MDM all-entity relationship processing. Relationship derivation and graph workflows may legitimately need non-operating and non-ticker entities; they must not inherit the company-identity filter.

### Daily filing artifacts

Daily artifact candidates should be bound to the exact accession union from the forced seven-day daily-index window. The filing path should process the relevant configured forms from those exact index accessions, not every historical recent or pagination accession belonging to an impacted CIK.

The exact-accession bound must preserve all relevant form families, including ownership, ADV, proxy, 13F, Item 5.02, and Item 2.02. Filing and relationship ingestion must not be filtered by SEC ticker presence.

On `PoolTimeout`, the runtime should reset the shared edgartools HTTP client and perform a bounded retry. Retry classification alone is insufficient when the shared connection pool remains exhausted.

## Follow-up implementation tickets

1. **Company-identity eligibility contract**
   - Define the active `(operating OR current-SEC-ticker-present)` contract in one testable boundary.
   - Apply it to daily company identity and the identity backstop only.
   - Emit the ticker snapshot identity and exact eligible/processed counts.
   - Prove MDM all-entity relationship processing remains independent.

2. **Exact daily-index accession and PoolTimeout bound**
   - Carry the forced seven-day daily-index accession union into artifact candidate selection.
   - Prevent submissions expansion from reintroducing unrelated historical recent/pagination accessions.
   - Preserve every configured relevant form family.
   - Reset the edgartools shared client before bounded `PoolTimeout` retry.
   - Emit exact index-accession, selected-candidate, network-fetch, retry, error, and elapsed-time counts.

## Release-readiness conclusion

The greater-than-six-hour behavior has two independent root causes and requires both bounds: a company-only identity universe and an exact daily-index accession universe for filing artifacts. Ticker filtering must never be applied to the whole filing or relationship pipeline.

PR #316's bounded path being merged is not deployment proof. Release readiness requires evidence from a deployed immutable candidate whose live state-machine definition and execution logs demonstrate both bounds and the required runtime counts.
