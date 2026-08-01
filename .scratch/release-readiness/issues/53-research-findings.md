# Research findings: why 3,082 daily CIKs became 148,524 artifact candidates

## Answer

The expansion was deterministic and reproducible. It was not caused by pagination,
duplicate accessions, or `PoolTimeout`.

The July 29 SEC form index supplied 5,969 rows, 5,807 distinct accessions, and
3,084 distinct CIKs. The daily command demoted the two CIKs that filed Form 15
(`720154` and `892553`), leaving 3,082 CIKs. At that point the implementation
discarded the daily-index accession set and retained only the CIK set.

For each of those 3,082 CIKs, the command loaded the issuer's complete SEC
submissions-main `filings.recent` array. It globally deduplicated 1,132,927
recent accessions, rejected 679,137 non-configured forms, and applied its two
configured lookbacks:

```text
1,132,927 distinct submissions-recent accessions
- 679,137 non-configured-form accessions
= 453,790 configured-form accessions before lookback

453,790
- 290,132 ownership accessions older than 2024-07-30
-  15,134 Item 5.02 accessions older than 2024-07-30
= 148,524 selected artifact candidates
```

This exactly reproduces all three live CloudWatch selection events. Because
`include_pagination=false`, all 453,790 configured candidates were from
submissions-main `filings.recent`; pagination contributed exactly zero.

The primary cause is a recurring-scope error: daily discovery is bounded by CIK
but artifact discovery reuses historical submissions enumeration originally
introduced to populate configured parsers. Catalog caching and parser
idempotency reduce network work, but neither changes that oversized candidate
set. `PoolTimeout` separately amplified elapsed time after selection.

## Immutable live identity

Read-only inspection on 2026-07-30/31 tied the evidence to:

- Step Functions execution:
  `arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-daily-incremental:daily-incremental-ticket03-1785413694`
- `RunWarehouseTask` ECS task definition: `edgartools-prod-large:90`
- ECS task:
  `arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/9cdc6464215b48809cf3b0fad5f405df`
- CloudWatch stream:
  `warehouse-large/edgar-warehouse/9cdc6464215b48809cf3b0fad5f405df`
- Warehouse image digest:
  `sha256:aca8078c658bc3f66ac40fa9e41923c4f29743f23ad5623756d94888728cbb30`
- ECR tags on that digest: `sha-4760be81bfdf`, `prod`
- Corresponding git commit:
  `4760be81bfdfe1a20cf09f6b195e19425cf25c20`

The current source differs from that deployed commit in the relevant
orchestrator file only by the later identity-refresh lease/window additions;
the daily artifact-selection and retry paths analyzed below are unchanged.

## Exact code and data path

1. The SEC daily-index loader preserves each row's accession in
   `edgar_warehouse/loaders/bronze_daily_index_extractors.py:15-69`.
2. `_load_daily_index_for_date` stages those rows and records a distinct
   accession count, but its return value contains impacted CIKs, not the
   accession set (`edgar_warehouse/application/warehouse_orchestrator.py:4243-4370`;
   deployed equivalent `:4104-4232`).
3. The daily branch deduplicates CIKs, seeds tracking state, demotes Form-15
   CIKs, filters to active tracking, and claims the remaining CIKs. It calls
   `_run_submissions_bronze_then_silver` with `include_pagination=False`,
   `recent_limit=None`, `artifact_policy=all_attachments`, and
   `parser_policy=configured_forms`
   (`warehouse_orchestrator.py:1038-1094`).
4. `stage_recent_filing_loader` reads the entire
   `filings.recent.accessionNumber` array and truncates only when
   `recent_limit` is supplied
   (`edgar_warehouse/loaders/bronze_submission_extractors.py:130-188`).
5. An unchanged submissions checkpoint does not suppress enumeration. The
   cached full payload is staged in memory again and all of its recent
   accessions are returned
   (`warehouse_orchestrator.py:3772-3816`). Changed snapshots likewise stage
   and return all recent accessions through
   `edgar_warehouse/silver_store.py:1714-1800`.
6. The shared routine globally deduplicates recent plus pagination accessions.
   Exact required-accession intersection exists only under `release_mode`;
   ordinary daily mode assigns the complete observed set to
   `artifact_accessions`
   (`warehouse_orchestrator.py:2623-2657`).
7. `_configured_parser_accessions` selects ownership, ADV, proxy, 13F,
   Item 5.02/ambiguous 8-K, and Item 2.02 8-K candidates. Only ownership and
   Item 5.02 receive two-year lookbacks; undated rows are retained
   (`warehouse_orchestrator.py:3271-3378`).
8. `filing_artifact_pipeline_started.accession_count` is therefore the
   post-form/post-lookback selection from historical submissions-recent
   arrays, not a daily-index accession count
   (`warehouse_orchestrator.py:2835-2875`).

`claim_discovery_ciks` is a concurrent-run exclusion mechanism, not an
accession completion checkpoint. It excludes another run's currently
`in_progress` CIK, but otherwise reclaims and overwrites the CIK discovery row
(`edgar_warehouse/silver_store.py:2552-2594`). It cannot prevent the same
historical accession enumeration on the next recurring daily run.

## Reconstructed candidate composition

The reconstruction read the exact official July 29 index and the exact latest
bronze submissions-main object that the live glob/cache policy selected for
each of the 3,082 CIKs. All 3,082 objects were present. The reproduced
148,524 candidates break down as follows.

### By configured family

| Family | Selected |
| --- | ---: |
| Ownership (Forms 3/4/5 and amendments) | 81,453 |
| Item 2.02 earnings 8-K | 30,380 |
| Proxy | 20,419 |
| 13F | 12,479 |
| Item 5.02 or ambiguous-items 8-K | 3,793 |
| ADV | 0 |
| **Total** | **148,524** |

The exact form counts were: Form 4 `74,178`; 8-K `33,788`; 13F-HR `11,885`;
DEF 14A `9,216`; DEFA14A `9,183`; Form 3 `5,545`; PRE 14A `2,020`;
Form 4/A `1,015`; 13F-HR/A `594`; Form 5 `520`; 8-K/A `385`;
Form 3/A `177`; Form 5/A `18`.

### By filing year

| Year | Selected | Year | Selected |
| ---: | ---: | ---: | ---: |
| 1994 | 36 | 2010 | 849 |
| 1995 | 32 | 2011 | 924 |
| 1996 | 57 | 2012 | 1,176 |
| 1997 | 55 | 2013 | 1,434 |
| 1998 | 58 | 2014 | 1,780 |
| 1999 | 113 | 2015 | 2,221 |
| 2000 | 144 | 2016 | 2,542 |
| 2001 | 158 | 2017 | 2,929 |
| 2002 | 195 | 2018 | 3,462 |
| 2003 | 187 | 2019 | 3,795 |
| 2004 | 249 | 2020 | 4,604 |
| 2005 | 395 | 2021 | 4,917 |
| 2006 | 463 | 2022 | 5,438 |
| 2007 | 553 | 2023 | 5,856 |
| 2008 | 636 | 2024 | 19,736 |
| 2009 | 840 | 2025 | 48,593 |
|  |  | 2026 | 34,097 |
|  |  | **Total** | **148,524** |

The pre-2024 proxy, 13F, and Item 2.02 rows remain because those families have
no recurring-run lookback. That is direct evidence that the selected list is
historical catch-up work rather than the July 29 accession set.

### Recent versus pagination and catalog cache

- Recent submissions-main: `148,524` selected (`100%`).
- Pagination: `0`.
- Selected candidates sourced from CIK payloads fetched from SEC during this
  run: `1,713`.
- Selected candidates sourced from previously captured submissions payloads:
  `146,811`.

The last two figures classify the *submissions catalog payload* that introduced
the accession, not whether the filing's attachments needed network. Live
bronze telemetry independently reported 540 submissions catalog network
fetches and 2,542 catalog cache hits across the 3,082 CIKs.

The run did not complete an attachment disposition for the full candidate
set, so a full `network-needed` versus `already-captured artifact` breakdown is
not authoritatively available. Before the circuit opened, final live artifact
metrics reported:

- `accessions_with_network=1,081`
- `accessions_silver_skip=303`
- `errors=140`
- `raw_object_count=7,736`
- `rows_written=8,373`

Ownership accessions with a successful current parse can take an additional
fast `continue` path and are not counted as network or silver-skip accessions.
That `continue` also bypasses the periodic progress event, explaining why the
last progress event said `processed=1,500` even though selection later moved
rapidly through many already-parsed ownership candidates.

## Why `PoolTimeout` was not reset or retried

Ordinary daily mode runs with `release_mode=False`. The artifact loop therefore
sets `artifact_attempts=1`; three attempts are enabled only for release mode
(`warehouse_orchestrator.py:2963-2967`).

On the first and only ordinary-mode failure, this condition is immediately
true:

```python
artifact_attempt >= artifact_attempts
```

The exception is re-raised before transient classification and before
`_reset_edgartools_client_after_pool_timeout` can execute
(`warehouse_orchestrator.py:2982-2990`). The outer per-accession handler logs
`filing_artifact_failed` and continues because only release mode fails closed
(`warehouse_orchestrator.py:3047-3060`).

Live proof:

- CloudWatch contained 20 `filing_artifact_failed` events whose error type was
  `PoolTimeout`.
- It contained zero `filing_artifact_retry` events.
- Individual `get_filing` failures waited roughly 82-94 seconds; the final two
  waited 83,360 ms and 83,501 ms.
- After 20 consecutive failures the loop emitted
  `filing_artifact_circuit_open`, then emitted
  `filing_artifact_pipeline_completed` rather than failing the command.

The circuit event's `remaining_accessions=140011` is not a reliable processed
count. The code subtracts `errors + rows_written` from the candidate count,
but `rows_written` counts attachment/parser rows rather than processed
accessions (`warehouse_orchestrator.py:2893-2901`).

Thus `PoolTimeout` added long waits after the 148,524 list already existed. It
did not create or multiply candidates.

## History and intent

Read-only `git log`, `git show`, and `git blame` establish:

- `24022fb` (2026-05-13) made daily incremental default to artifact fetch and
  configured parsers, feeding the combined recent/pagination accession set to
  fix empty ownership silver. This is the origin of the shared historical
  catch-up behavior.
- `505968e` (2026-07-06) added CIK discovery claims, which prevent concurrent
  work but do not checkpoint completed accessions across runs.
- `d20cad8` (2026-07-16) added exact required-accession bounding only for
  release mode. Ordinary mode deliberately retained
  `artifact_accessions = observed_accessions`.
- `c7daac4` restricted transient artifact retries to release mode.
- `2c26ecf` added the exhausted-client reset inside that release retry branch,
  leaving it unreachable for an ordinary one-attempt daily run.
- `19e7ad9` (2026-07-25) added two-year ownership and Item 5.02 filters.
- `0c1aa09` (2026-07-29) added Item 2.02 earnings 8-K selection without a
  lookback, increasing historical recurring candidates.

This is therefore mainly an accidental recurring-run consequence of reusing
bootstrap/catch-up-style submissions enumeration. It is not a failure to
deduplicate accessions: the 1,132,927 observed accessions were globally
deduplicated before selection. It is also not a bronze checkpoint failure:
2,542 of 3,082 submissions catalogs were reused from cache. The contract is
wrong at the handoff from exact daily-index accessions to CIK-only discovery.

## Narrow safe recurring-run contract

1. Preserve and carry the exact accession union from every forced daily-index
   date, alongside the impacted CIKs.
2. Continue staging submissions-main metadata when required, but intersect
   configured artifact selection with that exact daily-index accession union.
3. Preserve every configured family present in the daily index; do not apply
   the company-ticker eligibility rule to filing ingestion.
4. Keep full submissions-recent and pagination enumeration in explicitly named
   bootstrap, historical backfill, and repair workflows.
5. Reset the shared edgartools client before a bounded retry on ordinary-mode
   `PoolTimeout`; make circuit opening fail the recurring run.
6. Emit and fail closed on these invariants:
   - daily-index row, distinct-CIK, and distinct-accession counts;
   - selected artifact count and `selected / daily-index-accession` ratio;
   - recent and pagination candidate counts;
   - configured-form and per-lookback rejection counts;
   - catalog network/cache counts;
   - artifact network/cache/fast-parse-skip/retry/error counts;
   - circuit-open state and exact processed/remaining accession counts.

The recurring artifact candidate count must be a subset of the exact forced
daily-index accession union. Any selected accession outside that union is an
expansion-contract violation and must fail before attachment iteration.

## Reproduction commands

All AWS commands were read-only and used profile `sec_platform_deployer` in
`us-east-1`. No running task, state machine, S3 object, or AWS configuration was
mutated.

```bash
aws stepfunctions describe-execution \
  --execution-arn <execution-arn>

aws stepfunctions get-execution-history \
  --execution-arn <execution-arn> --max-results 1000

aws ecs describe-tasks \
  --cluster edgartools-prod-warehouse --tasks <task-arn>

aws ecs describe-task-definition \
  --task-definition edgartools-prod-large:90

aws ecr describe-images \
  --repository-name edgartools-prod-warehouse \
  --image-ids imageDigest=sha256:aca8078c658bc3f66ac40fa9e41923c4f29743f23ad5623756d94888728cbb30

aws logs filter-log-events \
  --log-group-name /aws/ecs/edgartools-prod-warehouse \
  --log-stream-names warehouse-large/edgar-warehouse/9cdc6464215b48809cf3b0fad5f405df \
  --filter-pattern filing_artifact_pipeline_started
```

The count reconstruction used:

- official SEC source:
  `https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260729.idx`;
- read-only S3 `ListObjectsV2` and `GetObject` against
  `edgartools-prod-bronze-690839588395`;
- the repository's own daily-index and submissions-recent loaders;
- the deployed commit's unchanged configured-form/lookback predicates.

The reconstruction asserted all 3,082 selected CIKs had an exact bronze
submissions-main object and reproduced the live `290132`, `15134`, and
`148524` events exactly.
