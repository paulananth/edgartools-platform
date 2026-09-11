# Data not available to agents (v1 Decision Contract)

Ticket: `.scratch/agent-decision-contract/issues/13-inventory-data-not-available-to-agents.md`

Live counts: `snow sql --connection edgartools-prod`, 2026-09-11,
[13-gold-counts.sql](13-gold-counts.sql). Graph views are the active
generation (`ae0db138-...` from research 11).

v1 **agent-grade** issuer sections (when a READY publication exists):
As-Of Decision Features, `IS_INSIDER`, `EMPLOYED_BY`.

Today **nothing is agent-grade in prod**: `EDGARTOOLS_DECISION` is an
empty schema (research 01). Agents have no published contract to pin.

**Inventory boundary:** Snowflake objects only. Bookkeeping Postgres and
bronze S3 are out of scope for agents (ADR 0001) and are not inventoried.

---

## 1. Not published

| Gap | Fact |
| --- | --- |
| Decision Contract views | `SUBJECT_FEATURE_SCREEN`, `SUBJECT_BUNDLE_READ*`, `DECISION_CONTRACT_PUBLICATION` **absent** |
| READY publication | no rows (table does not exist) |
| Universe snapshot | warehouse-active ∩ MDM-active is not a published Snowflake object |
| Bronze digest on watermark | required by ticket 03; nothing writes it yet (ticket 06 still open) |
| Gold `FINANCIAL_FACTORS` passthrough | code on `grok/agent-decision-data-plane-wayfinder`; prod still needs `dbt --full-refresh` |

Until READY + non-empty universe snapshot, Agent View ready-views would be
empty even if gold is full.

---

## 2. Locked unavailable on the issuer bundle

Ticket 05. Keys stay on the payload; not Trading Decision input.

| Section | Why unavailable | Live |
| --- | --- | --- |
| `holders_of_subject` / `subject_as_manager_portfolio` | no gold `issuer_cik`; graph `INSTITUTIONAL_HOLDS` = 97 vs 6.8M holdings | gold 6,799,919 |
| `auditor` | evidence 0; graph `AUDITED_BY` = 0 | SOURCE/SILVER 0 |
| `has_parent` | evidence 0; graph `HAS_PARENT_COMPANY` = 0 | SILVER 0 |
| issuer `adv` | `not_applicable` (pure issuer) | — |

---

## 3. Contract policy (out of this map / ADR 0001)

Agents must not treat these as Decision Contract input even when gold has
rows:

- Market prices / PE / mcap (`FORBIDDEN_MARKET_FIELDS`)
- Manager ADV / `MANAGES_FUND` / `IS_ENTITY_OF` agent-grade sections
- Filing text / NLP as Decision Features
- Trading execution, OAuth, MongoDB/JSON as the agent SoE

---

## 4. Explore-only gold (Agent View allowlist forbids unlabeled joins)

`AGENT_VIEW_ALLOWED_OBJECTS` is Decision Contract names only. These gold
tables exist and are **not** agent-grade:

| Gold table | Rows | Notes |
| --- | ---: | --- |
| `FINANCIAL_FACTS` | 434,805 | raw facts; v1 screen uses factors, not facts |
| `FINANCIAL_DERIVED` | 5,056 | upstream of factors |
| `FINANCIAL_FACTORS` | 5,056 | intended v1 vector **after** READY + refresh |
| `EARNINGS_RELEASES` | 918 | 8-K GAAP; not a v1 bundle section |
| `FILING_ACTIVITY` | 6,773,967 | filing index, not neighborhood |
| `FILING_DETAIL` | 6,773,967 | same |
| `OWNERSHIP_HOLDINGS` | 42,507 | accession bind only; no `OWNER_CIK`/`OWNER_NAME` |
| `OWNERSHIP_ACTIVITY` | 81,438 | not a v1 agent-grade section |
| `EXECUTIVE_RECORDS` | 14,755 | pay sidecar; not present without `EMPLOYED_BY` |
| `PRIVATE_FUNDS` | 414,968 | manager/ADV family; out of issuer v1 |
| `TICKER_REFERENCE` | 10,473 | resolver may use it; not a feature vector |
| `MDM_COMPANY` | 68,949 | identity, not the contract |
| `ADVISER_OFFICES` | 1 | manager family |

**Gold empty (would be Explore-only even if filled):**

| Gold table | Rows |
| --- | ---: |
| `ACCOUNTING_FLAGS` | 0 |
| `ADVISER_DISCLOSURES` | 0 |
| `CONSENSUS_ESTIMATES` | 0 |
| `EARNINGS_CALENDAR` | 0 |
| `GUIDANCE_FACTS` | 0 |
| `TRANSCRIPT_EVENTS` | 0 |

Consensus / guidance / transcripts / calendar are also ER-style surfaces
ADR 0001 kept out of Pure-SEC Decision Features.

---

## 5. Graph types not in issuer v1 agent-grade

| Edge view | Rows | Agent status |
| --- | ---: | --- |
| `IS_INSIDER` | 902 | v1 agent-grade (when published) |
| `EMPLOYED_BY` | 4,313 | v1 agent-grade (when published) |
| `INSTITUTIONAL_HOLDS` | 97 | locked unavailable |
| `AUDITED_BY` | 0 | locked unavailable |
| `HAS_PARENT_COMPANY` | 0 | locked unavailable |
| `HOLDS` | 395 | not a v1 issuer section |
| `COMPANY_HOLDS` | 3,148 | not a v1 issuer section |
| `ISSUED_BY` | 2,985 | not a v1 issuer section |
| `MANAGES_FUND` | 563,645 | manager bundle; out of this map |
| `IS_ENTITY_OF` | 0 | out of this map |

---

## 6. Bind gaps inside intended v1 sections

- Gold `OWNERSHIP_HOLDINGS` still has no person identity columns; insider
  join is graph-keyed + accession (ticket 05 Q4).
- `FINANCIAL_FACTORS` live columns still omit passthrough `ebitda` /
  `eps_diluted` / `ebitda_margin` until prod dbt `--full-refresh`.
- Gold `COMPANY.TRACKING_STATUS` is MDM, not warehouse-active. The
  warehouse-active predicate is not a Snowflake contract object. Bookkeeping
  Postgres is out of scope for agents and is not inventoried.

---

## 7. Continuation (2026-09-11) — columns, silver, graph nodes

SQL: [13-inventory-continued.sql](13-inventory-continued.sql). Pointer still
`ae0db138-...` (233,647 nodes / 575,485 edges). `EDGARTOOLS_DECISION`
still has **zero objects**.

### Live gold columns (bind still broken in prod)

| Object | Present | Missing for the contract |
| --- | --- | --- |
| `FINANCIAL_FACTORS` | `RETURN_ON_EQUITY`, `RETURN_ON_ASSETS`, `OPERATING_MARGIN` | `EBITDA`, `EPS_DILUTED`, `EBITDA_MARGIN`, `ROE`/`ROA` names (passthrough + aliases are in branch code, not live gold) |
| `OWNERSHIP_HOLDINGS` | `ACCESSION_NUMBER`, `OWNER_INDEX` | `OWNER_CIK`, `OWNER_NAME`, person entity id |
| `INSTITUTIONAL_HOLDINGS` | `CIK` (manager), `CUSIP`, `ISSUER_NAME`, `SHARES_HELD` | `ISSUER_CIK`, `MANAGER_CIK` |

### Silver has identity gold dropped

| Silver table | Rows | Agent access |
| --- | ---: | --- |
| `SEC_OWNERSHIP_REPORTING_OWNER` | 59,030 | **not** on the contract; gold dropped person columns |
| `SEC_EMPLOYMENT_EVENT` | 7,676 | graph `EMPLOYED_BY` is the v1 join, not this table |
| `SEC_THIRTEENF_FILING` | 14,364 | **not** on SOURCE (table absent); needed for effective 13F set |
| `SEC_AUDITOR_REPORT_EVIDENCE` | 0 | unavailable |
| `SEC_SUBSIDIARY_EVIDENCE` | 0 | unavailable |

SOURCE `SEC_AUDITOR_REPORT_EVIDENCE` = 0. SOURCE `SEC_THIRTEENF_FILING` **does not exist**.

### Graph nodes (active generation) — not issuer v1 sections

| `ENTITY_TYPE` | Nodes | Notes |
| --- | ---: | --- |
| company | 68,949 | matches `MDM_COMPANY_ENTITY` total, not the 63,197 active |
| person | 6,364 | vs 902 `IS_INSIDER` edges |
| fund | 130,615 | manager/ADV family |
| adviser | 24,449 | manager/ADV family |
| security | 3,270 | vs 97 `INSTITUTIONAL_HOLDS` |

Agents do not get fund/adviser/security neighborhoods in issuer v1.

### Universe counts still disagree

| Set | Rows |
| --- | ---: |
| Gold `COMPANY` | 73,691 |
| `MDM_COMPANY_ENTITY` | 68,949 |
| MDM-active | 63,197 |
| Graph company nodes | 68,949 |

Ticket 04 snapshot is unpublished, so none of these is the Decision Subject Universe.

### MDM mirror

Schema `EDGARTOOLS_PROD.MDM` has **19 tables**. Agents never read it
(CONTEXT: Snowflake Decision Contract only; no silver/bronze/MDM DSN).

---

## 8. Continuation — full schema sweep

SQL: [13-inventory-schemas.sql](13-inventory-schemas.sql),
[13-inventory-leftovers.sql](13-inventory-leftovers.sql).

Prod schemas: `EDGARTOOLS_DASHBOARD`, `EDGARTOOLS_DECISION` (empty),
`EDGARTOOLS_GOLD`, `EDGARTOOLS_SILVER`, `EDGARTOOLS_SILVER_LANDING`,
`EDGARTOOLS_SOURCE`, `MDM`, `MDM_GRAPH_REVIEW_DASHBOARD` (no tables),
`NEO4J_GRAPH_MIGRATION`, `PUBLIC` (no tables).

### Gold we had not listed

| Table | Rows | Agent status |
| --- | ---: | --- |
| `ADV_FUND_COUNT_RECONCILIATION` | 24,372 | Explore-only; manager/ADV |
| `MDM_ADVISER` | 24,449 | identity export, not contract |
| `MDM_FUND` | 130,615 | same |
| `MDM_PERSON` | 6,364 | same |
| `MDM_SECURITY` | 3,270 | same |
| `MDM_COMPANY` | view | same |

### Silver populated, not on the contract

| Table | Rows | Why agents miss it |
| --- | ---: | --- |
| `SEC_COMPANY_FILING` | 6,773,967 | filing index; Explore gold `FILING_*` |
| `SEC_FILING_ATTACHMENT` | 436,287 | artifacts, not Decision Features |
| `SEC_RAW_OBJECT` | 372,225 | bronze evidence bookkeeping |
| `SEC_COMPANY_ADDRESS` | 147,382 | identity detail |
| `SEC_COMPANY_TICKER` | 20,946 | gold `TICKER_REFERENCE` is the public ticker set |
| `SEC_ADV_PRIVATE_FUND` | 414,968 | manager/ADV |
| `SEC_ADV_FILING` | 61,223 | manager/ADV |
| `SEC_ADV_FIRM_ROSTER` | 47,457 | manager/ADV |
| `SEC_OWNERSHIP_NON_DERIVATIVE_TXN` | 78,469 | gold activity, not v1 agent-grade |
| `SEC_OWNERSHIP_DERIVATIVE_TXN` | 2,969 | same |

### Silver empty (would still be off-contract)

`SEC_FILING_TEXT` 0, `SEC_CURRENT_FILING_FEED` 0, `SEC_PCAOB_FIRM_IDENTITY` 0,
`SEC_ACCOUNTING_FLAG` 0, `SEC_ADV_DISCLOSURE_EVENT` 0, `SEC_GUIDANCE_FACT` 0.

Filing text is policy-out even if filled.

### Graph leftovers

| Object | Live |
| --- | --- |
| `GRAPH_EDGE_IS_PERSON_OF` | 0 |
| `GRAPH_NODE_AUDITFIRM` | 0 |
| `GRAPH_GENERATION` | 20 generations stored |
| `MDM_GRAPH_EDGES` (all gens) | 5,352,688 |
| `MDM_GRAPH_NODES` (all gens) | 2,052,673 |
| Native-app WCC smoke | 233,647 |
| Native-app BFS smoke | 0 |

Agents pin the **active** generation only (233,647 / 575,485). They do not
get Native App BFS/WCC, merge lineage, or retired generations.

### Human UIs, not the agent SoE

Two Streamlit apps exist (`EDGARTOOLS_DASHBOARD`, `MDM_GRAPH_REVIEW`).
Neither is the Decision Contract. Dashboard schemas have **no tables**.

This inventory stops at Snowflake. It will not continue into Bookkeeping
Postgres or bronze S3.
