# Live IS_INSIDER input completeness

Date: 2026-09-11
Connection: `snow sql --connection edgartools-prod` / `EDGARTOOLS_PROD`
SQL: [02-is-insider-input-completeness.sql](02-is-insider-input-completeness.sql),
[02-03-followup.sql](02-03-followup.sql)
Raw: [02-is-insider-input-completeness.out](02-is-insider-input-completeness.out),
[02-03-followup.out](02-03-followup.out)

Pointer: generation `ae0db138-2aeb-4e69-87ba-f812da92b2eb`, activated
2026-09-10, 233,647 nodes / 575,485 edges.

First-file `GROUP BY 1, 2` failed (Snowflake positional GROUP BY omitted
`TARGET_ENTITY_TYPE`). Follow-up with named GROUP BY succeeded.

## Graph (v1 join)

View `NEO4J_GRAPH_MIGRATION.GRAPH_EDGE_IS_INSIDER` includes
`SOURCE_ACCESSION` (confirmed `INFORMATION_SCHEMA` +
`snowflake_graph.py` view SQL).

| Measure | Live |
| --- | ---: |
| Edges | 902 |
| person → company | 902 |
| Distinct company targets | 88 |
| Distinct person sources | 342 |
| Edges with `SOURCE_ACCESSION` | 902 (all) |
| `EFFECTIVE_TO` null (current) | 902 (all) |
| Current + accession | 902 |
| `SOURCE_SYSTEM` | `ownership_filing` 902 |
| Distinct issuer CIKs on company nodes | 88 |
| Of those MDM-active (`MDM_COMPANY_ENTITY.tracking_status='active'`) | 87 |
| MDM-active companies (denominator) | 63,197 |

Ticket 05 `present` (≥1 current graph edge with source accession) is
satisfiable for **87 MDM-active issuers**. Gold-only names are not needed
for that rule. Coverage versus 63,197 MDM-active is sparse; empty vs
unavailable is a later grilling question.

## Gold (accession only)

`OWNERSHIP_HOLDINGS` columns: `FACT_KEY`, `COMPANY_KEY`, `DATE_KEY`,
`PARTY_KEY`, `SECURITY_KEY`, `ACCESSION_NUMBER`, `OWNER_INDEX`,
`SHARES_OWNED_AFTER`, `OWNERSHIP_DIRECT_INDIRECT`. **No** `OWNER_CIK`,
`OWNER_NAME`, or person entity id.

`OWNERSHIP_ACTIVITY` owner-like columns: `ACCESSION_NUMBER`,
`OWNERSHIP_TXN_TYPE_KEY`, `OWNER_INDEX` only.

| Object | Rows | Distinct `COMPANY_KEY` | Distinct accession |
| --- | ---: | ---: | ---: |
| Gold `OWNERSHIP_HOLDINGS` | 42,507 | 4,577 | 39,094 |
| Gold `OWNERSHIP_ACTIVITY` | 81,438 | 4,579 | — |

Gold has far more issuer keys than the graph (4,577 vs 88). Those extra
gold rows cannot mark `present` under ticket 05 (gold-only strings never
`present`).

## Silver (identity gold dropped)

`EDGARTOOLS_SILVER.SEC_OWNERSHIP_REPORTING_OWNER`: 59,030 rows. Columns
include `OWNER_CIK`, `OWNER_NAME`, `CIK`, `MDM_ENTITY_ID`,
`ACCESSION_NUMBER`, `OWNER_INDEX`, director/officer flags. Agents must not
read silver (ADR 0001); this is why graph-keyed identity exists.

Does not decide whether gold must grow person columns (grilling ticket 04).
