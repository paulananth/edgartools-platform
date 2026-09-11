# Live EMPLOYED_BY input completeness

Date: 2026-09-11
Connection: `snow sql --connection edgartools-prod` / `EDGARTOOLS_PROD`
SQL: [03-employed-by-input-completeness.sql](03-employed-by-input-completeness.sql),
[02-03-followup.sql](02-03-followup.sql)
Raw: [03-employed-by-input-completeness.out](03-employed-by-input-completeness.out),
[02-03-followup.out](02-03-followup.out)

Pointer: generation `ae0db138-2aeb-4e69-87ba-f812da92b2eb`, activated
2026-09-10, 233,647 nodes / 575,485 edges.

Same first-file `GROUP BY 1, 2` failure as ticket 02; follow-up succeeded.

## Graph (v1 join)

View `GRAPH_EDGE_EMPLOYED_BY` includes `SOURCE_SYSTEM` and
`SOURCE_ACCESSION`.

| Measure | Live |
| --- | ---: |
| Edges | 4,313 |
| person → company | 4,313 |
| Distinct company targets | 1,356 |
| Distinct person sources | 3,817 |
| Edges with `SOURCE_ACCESSION` | 4,313 (all) |
| `EFFECTIVE_TO` null (current) | 4,018 |
| Distinct issuer CIKs | 1,356 |
| Of those MDM-active | 1,351 |
| MDM-active companies | 63,197 |

### Source-system names (bind risk)

Ticket 05 `present` names sources `proxy_def14a` or `item_5_02`.

Live `SOURCE_SYSTEM` on the active generation:

| `SOURCE_SYSTEM` | Edges |
| --- | ---: |
| `item_502_filing` | 4,268 |
| `proxy_filing` | 45 |

Those are **not** the ticket 05 tokens. If Agent View / bundle SQL
literal-matches `proxy_def14a` / `item_5_02`, every live edge would fail
`present` and look `unavailable` or `non_agent_grade`. Grilling ticket 04
must lock the allowed source tokens against this live vocabulary.

## Silver

`EDGARTOOLS_SILVER.SEC_EMPLOYMENT_EVENT`: 7,676 rows. Columns:
`ACCESSION_NUMBER`, `EVENT_INDEX`, `CIK`, `EVENT_TYPE`, `PERSON_NAME`,
`EXEC_ROLE`, `PREVIOUS_ROLE`, `COMPENSATION_AMOUNT`, `EFFECTIVE_DATE`,
`PARSER_VERSION`, `INGESTED_AT`. Not on the contract.

## Gold pay sidecar (ticket 05: `non_agent_grade`)

`EXECUTIVE_RECORDS`: 14,755 rows, 903 distinct CIKs (all 903 MDM-active),
2,270 accessions. 13,491 have `TOTAL_COMP`; all 14,755 have `EXEC_NAME`.
Columns are pay/role (`EXEC_NAME`, `EXEC_ROLE`, `TOTAL_COMP`, awards) plus
`CIK` / `ACCESSION_NUMBER`. No graph person id. Ticket 05: pay-only gold
is never `present`.

Graph employment issuers (1,351 MDM-active) and gold exec issuers (903)
are different sets; gold is not a substitute for the graph section.

Does not decide the usable-identity bar (grilling ticket 04).
