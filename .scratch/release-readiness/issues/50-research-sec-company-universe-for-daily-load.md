# Research the SEC-listed company universe for bounded daily loads

Type: research
Status: resolved
Blocked by: (none)

## Question

Why did the observed production `daily_incremental` execution run for more
than six hours, and should the Daily Identity Refresh and/or Identity Backstop
Sweep replace the platform's approximately 26,300-CIK tracked universe with
the SEC `company_tickers.json` universe?

Resolve with direct evidence:

1. Attribute the observed runtime to specific Step Functions states, Map runs,
   ECS tasks, commands, item counts, concurrency, retries, and downstream
   stages. Distinguish the historical execution from the implementation now
   merged under “Implement and Activate the Bounded Daily Identity Refresh
   Schedule.”
2. Fetch the current SEC `company_tickers.json` and
   `company_tickers_exchange.json` primary-source datasets and report record
   counts, distinct CIK counts, duplicate-CIK/ticker behavior, and the actual
   population size. Verify rather than assume the proposed “3,000+” estimate.
3. Compare that population with the platform's tracked universe and identify
   which entity types and required workflows would be excluded by using the
   ticker file as the eligibility boundary.
4. Decide separately whether the ticker universe is appropriate for:
   - the daily impacted-CIK refresh;
   - the weekly full-universe identity backstop;
   - downstream MDM, relationship, gold, and dashboard processing.
5. Recommend a precise, testable universe contract that avoids processing
   irrelevant non-company CIKs while preserving required SEC registrants and
   release-readiness coverage. Identify implementation and evidence tickets
   that should change, but do not modify runtime code or production AWS.

Use primary sources only: live read-only AWS execution metadata/logs, official
SEC datasets/documentation, repository source and git history, and canonical
warehouse/MDM evidence. Record uncertainty explicitly where live evidence is
unavailable.

## Answer

Full evidence and source citations are in
[Research findings: bound daily identity to companies, daily artifacts to exact
index accessions](50-research-findings.md).

The greater-than-six-hour behavior has two independent causes:

1. The old live state machine processed approximately 26,300 active tracked
   CIKs through `Stage0CompanyIdentity`; the current observed run spent 9h56m
   in that stage. The merged bounded definition was not deployed.
2. The same run's already-narrow `RunWarehouseTask` started with 3,082
   daily-index CIKs but expanded them into 148,524 historical artifact
   candidates. Repeated 82–94 second `PoolTimeout` failures then made the
   artifact pass operationally unbounded.

The official SEC ticker file is not itself a 3,000-company global universe:
it currently has 10,432 ticker rows representing 8,017 distinct CIKs. The
approximately-3,000 platform scope is the active tracked company-eligible
union:

```text
entity_type = operating
OR CIK is present in the current official SEC ticker snapshot
```

The canonical snapshot yields 3,243 CIKs for that union. It is the accepted
scope for scheduled company-identity refresh and backstop processing; the
count must be calculated and emitted at runtime, never hard-coded.

Ticker presence must not gate the whole daily filing or relationship path.
Only 84 of the 3,084 CIKs in the SEC 2026-07-29 master index appeared in the
ticker file. A whole-pipeline ticker filter would discard 3,000 daily filers,
including required Form 4 and Form 13F participants.

Daily artifact work instead must be bounded to the exact accession union from
the forced seven-day daily-index window. `PoolTimeout` handling must reset the
shared edgartools HTTP client before a bounded retry. MDM all-entity
relationship processing remains independent from the company-identity filter.

Implementation is graduated to
[Implement the company-only identity refresh universe](51-implement-company-only-identity-refresh-universe.md)
and
[Bind daily artifacts to the forced-index accession union](52-bind-daily-artifacts-to-index-accessions.md).
No code, AWS resources, running executions, or schedules were mutated by this
research.
