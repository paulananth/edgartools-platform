# Refresh: issuer neighborhood live counts after rebase

Date: 2026-09-10 (after `origin/main` `ea9fadbb`, PRs #581/#582).

Live `snow sql --connection edgartools-prod` against `EDGARTOOLS_PROD`.
SQL: [11-refresh-neighborhood-counts.sql](11-refresh-neighborhood-counts.sql).
Prior inventory: [08-issuer-neighborhood-evidence.md](08-issuer-neighborhood-evidence.md)
(generation `a573ebba-...`, activated 2026-08-22).

## Active graph

| | 08 inventory | This refresh |
| --- | --- | --- |
| `GRAPH_ACTIVE_POINTER` | `a573ebba-5820-49f2-8c40-43a4f538a79b` | `ae0db138-2aeb-4e69-87ba-f812da92b2eb` |
| Activated | 2026-08-22 | 2026-09-10 16:15:24 -0700 |
| Nodes / edges | 226,197 / 621,201 | 233,647 / 575,485 |

Matches the Ticket 10 rebuild in
`.scratch/mdm-relationship-versioning-gap/` (INSTITUTIONAL_HOLDS +
HOLDS / EMPLOYED_BY / IS_INSIDER quarantine backfill, then graph
rebuild). Edge total fell because duplicate quarantined edges were
dropped; node count rose.

## Neighborhood graph edges (active views)

| View | 08 inventory | This refresh |
| --- | ---: | ---: |
| `GRAPH_EDGE_IS_INSIDER` | 1,617 | **902** |
| `GRAPH_EDGE_EMPLOYED_BY` | 3 | **4,313** |
| `GRAPH_EDGE_INSTITUTIONAL_HOLDS` | 0 | **97** |
| `GRAPH_EDGE_AUDITED_BY` | 0 | 0 |
| `GRAPH_EDGE_HAS_PARENT_COMPANY` | 0 | 0 |
| `GRAPH_EDGE_HOLDS` | (not in 08 minimum set) | 395 |
| `GRAPH_EDGE_COMPANY_HOLDS` | (not in 08 minimum set) | 3,148 |

`IS_INSIDER` dropped because the backfill closed duplicate versions.
`EMPLOYED_BY` is now a real neighborhood, not an empty graph.
`INSTITUTIONAL_HOLDS` is no longer zero, but 97 edges against 6.8M gold
holdings is not a complete bind.

## Gold / silver (unchanged bind gaps)

| Object | Count | Bind note |
| --- | ---: | --- |
| Gold `INSTITUTIONAL_HOLDINGS` | 6,799,919 | Still **no** `ISSUER_CIK` column |
| Gold `OWNERSHIP_HOLDINGS` | 42,507 | Still no `OWNER_CIK` / `OWNER_NAME`; accession + `OWNER_INDEX` only |
| Gold `EXECUTIVE_RECORDS` | 14,755 | Unchanged |
| Gold `FINANCIAL_FACTORS` | 5,056 | Features exist |
| Silver/SOURCE auditor evidence | 0 | Unchanged |
| Silver subsidiary evidence | 0 | Unchanged |
| Silver `SEC_EMPLOYMENT_EVENT` | 7,676 | Unchanged |
| Gold `MDM_COMPANY_ENTITY` active | 63,197 | Unchanged |
| Gold `COMPANY` | 73,691 | Was ~67,939 in 08 (warehouse-only tail grew; PR #582 stops *new* individual-filer rows, does not purge existing) |

## What this changes for ticket 05 Q1

- **Do not treat `EMPLOYED_BY` as graph-empty.** It is now the second
  neighborhood with material graph + gold/silver evidence.
- **Do not promote `holders_of_subject` to agent-grade** on 97 graph
  edges and no `issuer_cik`.
- **Auditor / parent** remain 0 everywhere — still `unavailable`, not
  `empty`.
- **`IS_INSIDER` remains bindable** (902 edges + gold accessions) even
  though gold still lacks person identity columns; join is still
  graph-keyed per Ticket 11.
