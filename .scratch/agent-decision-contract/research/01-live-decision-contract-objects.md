# Live Decision Contract, graph-pointer, and universe objects

Ticket: `.scratch/agent-decision-contract/issues/01-inventory-live-decision-contract-objects.md`

Date: 2026-09-10

Method: live prod Snowflake via `snow sql --connection edgartools-prod` as
`ACCOUNTADMIN` on `EDGARTOOLS_PROD`, plus in-repo SQL/Terraform that created
the empty schema and reader grants. No secrets dumped.

Session identity (live):

```text
CURRENT_ORGANIZATION_NAME = PRJEDJU
CURRENT_ACCOUNT_NAME      = QJB05385
CURRENT_DATABASE          = EDGARTOOLS_PROD
CURRENT_ROLE              = ACCOUNTADMIN
CURRENT_WAREHOUSE         = COMPUTE_WH
```

Primary sources:

- Live `INFORMATION_SCHEMA` / `SHOW` / `COUNT` / `SELECT` against `EDGARTOOLS_PROD`
- `infra/snowflake/sql/bootstrap/15_decision_schema.sql`
- `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql`
- `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`
- `infra/snowflake/sql/decision_contract/03_dashboard_contract.sql`
- `infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql`
- `infra/snowflake/dbt/edgartools_gold/models/gold/company.sql`
- `infra/scripts/deploy-snowflake-stack.sh` (applies `15_decision_schema.sql`)
- `infra/terraform/access/snowflake/modules/account_access/main.tf`
- `edgar_warehouse/mdm/snowflake_graph.py` (`GRAPH_ACTIVE_POINTER` DDL)

---

## Summary answers

1. **`EDGARTOOLS_DECISION` exists and is empty.** Created 2026-08-18 with the
   bootstrap comment that views are not yet built. Zero tables, zero views.
   `DECISION_CONTRACT_PUBLICATION` does not exist, so there are no READY rows.
2. **`NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER` exists** (1 row).
   `POINTER_ID='active'` points at generation
   `a573ebba-5820-49f2-8c40-43a4f538a79b`, activated 2026-08-22. Later
   verified/building generations exist; none of them is the active pointer.
3. **`EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY` exists with `TRACKING_STATUS`.**
   68,949 rows; 63,197 `active` (1:1 distinct CIKs). Gold `COMPANY` is a
   dynamic table that copies that MDM column via left join: the 63,197
   `active` CIKs match exactly. `COMPANY` has 4,742 extra warehouse-only
   rows with no MDM `ENTITY_ID`.
4. **`SUBJECT_FEATURE_SCREEN` and `SUBJECT_BUNDLE_READ_ISSUER` are absent**,
   not empty. Live `SELECT` against either object fails
   `does not exist or not authorized`.
5. **Roles that can use the schema today:** `ACCOUNTADMIN` (OWNERSHIP);
   `EDGARTOOLS_PROD_READER` (USAGE + FUTURE SELECT on VIEWS);
   `EDGARTOOLS_PROD_DASHBOARD_OWNER` and `SYSADMIN` inherit the reader role.
   No current views exist, so the future-view grant has nothing to attach to.
   No SELECT is granted on tables.

The in-repo `decision_contract/*.sql` sketches were **not applied**. Live
prod has only the empty schema container from
`15_decision_schema.sql` plus Terraform reader grants.

---

## 1. Schema `EDGARTOOLS_DECISION` and `DECISION_CONTRACT_PUBLICATION`

### Schema exists

Live `INFORMATION_SCHEMA.SCHEMATA`:

| SCHEMA_NAME | CREATED | COMMENT |
| --- | --- | --- |
| `EDGARTOOLS_DECISION` | 2026-08-18T03:46:05.482000-07:00 | `Decision Contract schema (GH-247) -- reader-grant target only; views not yet built, see infra/snowflake/sql/decision_contract/*.sql` |

Query:

```sql
SELECT SCHEMA_NAME, CREATED, LAST_ALTERED, COMMENT
FROM EDGARTOOLS_PROD.INFORMATION_SCHEMA.SCHEMATA
ORDER BY SCHEMA_NAME;
```

The live comment is byte-identical to
`infra/snowflake/sql/bootstrap/15_decision_schema.sql` lines 41–42:

```sql
CREATE SCHEMA IF NOT EXISTS IDENTIFIER($decision_schema_name)
  COMMENT = 'Decision Contract schema (GH-247) -- reader-grant target only; views not yet built, see infra/snowflake/sql/decision_contract/*.sql';
```

`deploy-snowflake-stack.sh` (lines 422–443) is the apply path: it `SET`s
`database_name` / `decision_schema_name='EDGARTOOLS_DECISION'` and pipes
`15_decision_schema.sql` through `snow sql`. That bootstrap file
deliberately does **not** create views; its header says the
`decision_contract/*.sql` sketches remain unapplied.

`SHOW SCHEMAS LIKE 'EDGARTOOLS_DECISION' IN DATABASE EDGARTOOLS_PROD`
returned one row, owner role `ACCOUNTADMIN`, created 2026-08-18 03:46:05.

### Holds no tables or views

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ROW_COUNT, CREATED, LAST_ALTERED, COMMENT
FROM EDGARTOOLS_PROD.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'EDGARTOOLS_DECISION'
ORDER BY TABLE_TYPE, TABLE_NAME;
-- result: No data
```

```sql
SHOW OBJECTS IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_DECISION;
-- result: []
```

### No READY publication rows — table is absent

```sql
SELECT COUNT(*) AS n
FROM EDGARTOOLS_PROD.EDGARTOOLS_DECISION.DECISION_CONTRACT_PUBLICATION;
```

Error (live, ACCOUNTADMIN, so this is absence not authorization):

```text
002003 (42S02): SQL compilation error:
Object 'EDGARTOOLS_PROD.EDGARTOOLS_DECISION.DECISION_CONTRACT_PUBLICATION'
does not exist or not authorized.
```

There is therefore **no READY-row count to report**. The sketch table in
`03_dashboard_contract.sql` (`CREATE TABLE IF NOT EXISTS ...
DECISION_CONTRACT_PUBLICATION`, `PUBLICATION_STATUS STRING NOT NULL`) was
never created. Do not infer 0 READY rows from an object that does not exist.

### Sketch objects expected vs live

From the three sketch files, none of the following exist in prod:

| Sketch object | Source file | Live |
| --- | --- | --- |
| `SUBJECT_FEATURE_SCREEN` (view) | `01_subject_feature_screen.sql` | absent |
| `BUNDLE_HOLDERS_OF_SUBJECT` (view) | `02_subject_bundle_read_issuer.sql` | absent |
| `BUNDLE_AUDITOR` (view) | `02_subject_bundle_read_issuer.sql` | absent |
| `DECISION_CONTRACT_PUBLICATION` (table) | `03_dashboard_contract.sql` | absent |
| `DECISION_CONTRACT_STATUS` (view) | `03_dashboard_contract.sql` | absent |
| `SUBJECT_BUNDLE_READ_ISSUER` (view) | `03_dashboard_contract.sql` | absent |
| `SUBJECT_BUNDLE_READ` (view) | `03_dashboard_contract.sql` | absent |
| `DECISION_CONTRACT_DISPLAY_STATUS` (view) | `03_dashboard_contract.sql` | absent |
| `SUBJECT_BUNDLE_DISPLAY_ISSUER` (view) | `03_dashboard_contract.sql` | absent |
| `DASHBOARD_SUBJECT_RESOLVER` (view) | `03_dashboard_contract.sql` | absent |

Filename vs body mismatch: `02_subject_bundle_read_issuer.sql` does **not**
create `SUBJECT_BUNDLE_READ_ISSUER`. It creates `BUNDLE_HOLDERS_OF_SUBJECT`
and `BUNDLE_AUDITOR`. The object named `SUBJECT_BUNDLE_READ_ISSUER` is
defined only in `03_dashboard_contract.sql`.

`02_subject_bundle_read_issuer.sql` also uses an unqualified
`CREATE SCHEMA IF NOT EXISTS EDGARTOOLS_DECISION` (no `{{ database }}`
prefix), unlike `01` and `03`. That sketch was not applied, so the
unqualified name did not affect live prod.

---

## 2. `NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER`

Schema `NEO4J_GRAPH_MIGRATION` exists (created 2026-08-22T03:50:17.143000-07:00).

Live `INFORMATION_SCHEMA.TABLES`:

| TABLE_NAME | TABLE_TYPE | ROW_COUNT | CREATED | LAST_ALTERED |
| --- | --- | --- | --- | --- |
| `GRAPH_ACTIVE_POINTER` | BASE TABLE | 1 | 2026-08-22T07:33:58.251000-07:00 | 2026-08-22T13:45:49.337000-07:00 |
| `GRAPH_GENERATION` | BASE TABLE | 18 | 2026-08-22T07:33:57.925000-07:00 | 2026-09-06T07:15:40.959000-07:00 |
| `MDM_GRAPH_NODES` | BASE TABLE | 1,585,379 | 2026-08-22T07:33:59.256000-07:00 | 2026-09-06T07:15:22.998000-07:00 |
| `MDM_GRAPH_EDGES` | BASE TABLE | 4,201,718 | 2026-08-22T07:34:03.912000-07:00 | 2026-09-06T07:15:27.165000-07:00 |

Pointer contents:

```sql
SELECT POINTER_ID, ACTIVE_GENERATION_ID, ACTIVATED_AT
FROM EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER;
```

| POINTER_ID | ACTIVE_GENERATION_ID | ACTIVATED_AT |
| --- | --- | --- |
| `active` | `a573ebba-5820-49f2-8c40-43a4f538a79b` | 2026-08-22T13:45:46.956000-07:00 |

That matches the sketch join in `03_dashboard_contract.sql`
(`ptr.POINTER_ID = 'active'`). Column names match the DDL in
`edgar_warehouse/mdm/snowflake_graph.py` (`POINTER_ID`,
`ACTIVE_GENERATION_ID`, `ACTIVATED_AT`).

The pointed-at generation row:

```sql
SELECT GENERATION_ID, STATUS, RULE_VERSION, SCHEMA_VERSION,
       NODE_COUNT, EDGE_COUNT, CREATED_AT, VERIFIED_AT, ACTIVATED_AT, RETIRED_AT
FROM EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION
WHERE GENERATION_ID = 'a573ebba-5820-49f2-8c40-43a4f538a79b';
```

| Field | Value |
| --- | --- |
| STATUS | `activated` |
| RULE_VERSION / SCHEMA_VERSION | `v1` / `v1` |
| NODE_COUNT / EDGE_COUNT | 226,197 / 621,201 |
| CREATED_AT | 2026-08-22T07:33:58.537000-07:00 |
| VERIFIED_AT | 2026-08-22T13:44:01.608000-07:00 |
| ACTIVATED_AT | 2026-08-22T13:45:48.225000-07:00 |
| RETIRED_AT | NULL |

`GRAPH_GENERATION` has 18 rows total. Status mix (live `GROUP BY STATUS`):

| STATUS | N | latest CREATED_AT | latest ACTIVATED_AT |
| --- | --- | --- | --- |
| `activated` | 1 | 2026-08-22 | 2026-08-22T13:45:48 |
| `verified` | 4 | 2026-08-30 | NULL |
| `failed` | 1 | 2026-08-29 | NULL |
| `building` | 12 | 2026-09-06T07:15:19 | NULL |

The active pointer has not moved since 2026-08-22 even though later
generations were written (nodes/edges `LAST_ALTERED` 2026-09-06). That is
inventory, not a verdict on whether those later generations should be
activated.

`MDM_GRAPH_REVIEW` is **not** a live schema in `EDGARTOOLS_PROD`. The
closest name is `MDM_GRAPH_REVIEW_DASHBOARD` (Streamlit schema, created
2026-08-18). Graph-pointer inventory is the `NEO4J_GRAPH_MIGRATION`
objects above.

---

## 3. `EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY` vs gold `COMPANY` tracking

Both objects exist.

```sql
SELECT TABLE_NAME, TABLE_TYPE, IS_DYNAMIC, ROW_COUNT
FROM EDGARTOOLS_PROD.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'EDGARTOOLS_GOLD'
  AND TABLE_NAME IN ('COMPANY', 'MDM_COMPANY_ENTITY', 'MDM_COMPANY');
```

| TABLE_NAME | TABLE_TYPE | IS_DYNAMIC | ROW_COUNT (information_schema) |
| --- | --- | --- | --- |
| `MDM_COMPANY_ENTITY` | BASE TABLE | NO | 68,949 |
| `COMPANY` | BASE TABLE | YES | 73,691 |
| `MDM_COMPANY` | VIEW | NO | null |

`MDM_COMPANY_ENTITY` is the physical export target created by
`infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql` (includes
`tracking_status VARCHAR`). `COMPANY` is the dbt gold dynamic table
(`infra/snowflake/dbt/edgartools_gold/models/gold/company.sql`) that left
joins `source('mdm_export', 'MDM_COMPANY_ENTITY')` and selects
`m.tracking_status`. `MDM_COMPANY` is the compat view over the same
physical table (`mdm_company.sql`).

Live columns include `TRACKING_STATUS TEXT NULL` on both
`MDM_COMPANY_ENTITY` and `COMPANY` (`INFORMATION_SCHEMA.COLUMNS`).

Live `COUNT(*)` by `TRACKING_STATUS`:

```sql
SELECT 'MDM_COMPANY_ENTITY' AS src, COALESCE(TRACKING_STATUS, '<NULL>') AS tracking_status, COUNT(*) AS n
FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY
GROUP BY 1, 2
UNION ALL
SELECT 'COMPANY', COALESCE(TRACKING_STATUS, '<NULL>'), COUNT(*)
FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY
GROUP BY 1, 2;
```

| src | tracking_status | n |
| --- | --- | --- |
| `MDM_COMPANY_ENTITY` | `active` | 63,197 |
| `MDM_COMPANY_ENTITY` | `bootstrap_pending` | 9 |
| `MDM_COMPANY_ENTITY` | `<NULL>` | 5,743 |
| `COMPANY` | `active` | 63,197 |
| `COMPANY` | `bootstrap_pending` | 9 |
| `COMPANY` | `<NULL>` | 10,485 |

MDM active CIKs are complete and unique:

```sql
SELECT COUNT(*) AS active_rows, COUNT(CIK) AS active_with_cik,
       COUNT(DISTINCT CIK) AS distinct_active_ciks,
       COUNT_IF(CIK IS NULL) AS active_cik_null
FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY
WHERE LOWER(COALESCE(TRACKING_STATUS, '')) = 'active';
-- 63197 / 63197 / 63197 / 0
```

Gold `COMPANY` join coverage:

```sql
SELECT COUNT(*) AS company_rows,
       COUNT_IF(LOWER(COALESCE(TRACKING_STATUS, '')) = 'active') AS company_active,
       COUNT_IF(ENTITY_ID IS NULL) AS company_no_mdm_entity,
       COUNT_IF(ENTITY_ID IS NOT NULL) AS company_with_mdm_entity
FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY;
-- 73691 / 63197 / 4742 / 68949
```

Active-set anti-joins both returned 0:

```sql
-- MDM-active CIKs missing from COMPANY-active: 0
-- COMPANY-active CIKs missing from MDM-active: 0
```

So today:

- Sketch `01_subject_feature_screen.sql` universe
  (`MDM_COMPANY_ENTITY` where `tracking_status='active'` and `cik IS NOT NULL`)
  is **63,197 CIKs**.
- Sketch `03_dashboard_contract.sql` `tracked` CTE
  (`COMPANY` where `tracking_status='active'`) is the **same 63,197 CIKs**.
- That equality is because `COMPANY.TRACKING_STATUS` is the MDM column
  copied by the left join, not an independent warehouse-active flag.
- The 4,742 `COMPANY` rows with `ENTITY_ID IS NULL` have NULL tracking
  (warehouse companies with no MDM golden record). Combined with the
  5,743 MDM rows that themselves have NULL tracking, that accounts for
  `COMPANY`'s 10,485 NULL-tracking rows (4,742 + 5,743).

Ticket 04 still has to name the warehouse-active predicate; this ticket
only records that gold `COMPANY.TRACKING_STATUS` currently mirrors MDM.

---

## 4. `SUBJECT_FEATURE_SCREEN` / `SUBJECT_BUNDLE_READ_ISSUER`

**Absent**, not deployed-and-empty.

```sql
SELECT COUNT(*) FROM EDGARTOOLS_PROD.EDGARTOOLS_DECISION.SUBJECT_FEATURE_SCREEN;
-- 002003 (42S02): Object '...SUBJECT_FEATURE_SCREEN' does not exist or not authorized.

SELECT COUNT(*) FROM EDGARTOOLS_PROD.EDGARTOOLS_DECISION.SUBJECT_BUNDLE_READ_ISSUER;
-- 002003 (42S02): Object '...SUBJECT_BUNDLE_READ_ISSUER' does not exist or not authorized.
```

A name search across the database found neither object (nor
`DECISION_CONTRACT_PUBLICATION`, `BUNDLE_HOLDERS_OF_SUBJECT`,
`BUNDLE_AUDITOR`):

```sql
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ROW_COUNT
FROM EDGARTOOLS_PROD.INFORMATION_SCHEMA.TABLES
WHERE TABLE_NAME IN (
  'SEC_AUDITOR_REPORT_EVIDENCE',
  'SUBJECT_FEATURE_SCREEN',
  'SUBJECT_BUNDLE_READ_ISSUER',
  'DECISION_CONTRACT_PUBLICATION',
  'BUNDLE_HOLDERS_OF_SUBJECT',
  'BUNDLE_AUDITOR'
);
```

Dependencies the sketches would read, for contrast (these **do** exist):

| Object | Live | ROW_COUNT (information_schema) |
| --- | --- | --- |
| `EDGARTOOLS_GOLD.FINANCIAL_FACTORS` | dynamic table | 5,056 |
| `EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS` | dynamic table | 6,799,919 |
| `EDGARTOOLS_SOURCE.SEC_AUDITOR_REPORT_EVIDENCE` | table | 0 |
| `EDGARTOOLS_SILVER.SEC_AUDITOR_REPORT_EVIDENCE` | table | 0 |
| `EDGARTOOLS_SILVER_LANDING.SEC_AUDITOR_REPORT_EVIDENCE` | table | 0 |
| `EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE` | **absent** | — |

`02_subject_bundle_read_issuer.sql` already points `BUNDLE_AUDITOR` at
`EDGARTOOLS_SOURCE.SEC_AUDITOR_REPORT_EVIDENCE` (that SOURCE table exists
and is empty). There is still no gold-layer copy.

---

## 5. Grants on `EDGARTOOLS_DECISION`

Live `SHOW GRANTS ON SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_DECISION`:

| privilege | granted_on | grantee_name | created_on |
| --- | --- | --- | --- |
| OWNERSHIP | SCHEMA | `ACCOUNTADMIN` | 2026-08-18T03:46:05 |
| USAGE | SCHEMA | `EDGARTOOLS_PROD_READER` | 2026-08-18T03:48:37 |

Live `SHOW FUTURE GRANTS IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_DECISION`:

| privilege | grant_on | name | grantee_name | created_on |
| --- | --- | --- | --- | --- |
| SELECT | VIEW | `EDGARTOOLS_PROD.EDGARTOOLS_DECISION.<VIEW>` | `EDGARTOOLS_PROD_READER` | 2026-08-18T03:48:38 |

Those two reader grants match Terraform
`infra/terraform/access/snowflake/modules/account_access/main.tf`:

- `reader_decision_schema_usage` — USAGE on `local.decision_schema_fqn`
- `reader_decision_future_views` — SELECT on future VIEWS in that schema
- `reader_decision_all_views` — SELECT on all current VIEWS (currently none,
  so this grant has nothing to list under `SHOW GRANTS ON SCHEMA`)

`SHOW GRANTS OF ROLE EDGARTOOLS_PROD_READER`:

| granted_to | grantee_name |
| --- | --- |
| ROLE | `EDGARTOOLS_PROD_DASHBOARD_OWNER` |
| ROLE | `SYSADMIN` |

`reader_to_dashboard_owner` in the same Terraform module grants the reader
role to `dashboard_owner`. SYSADMIN also holds it (live, not declared in
that module snippet).

Who can SELECT contract objects **if views existed today**:

- `ACCOUNTADMIN` — schema OWNERSHIP
- `EDGARTOOLS_PROD_READER` — USAGE + future VIEW SELECT
- `EDGARTOOLS_PROD_DASHBOARD_OWNER` — inherits reader
- `SYSADMIN` — inherits reader

Who cannot, from schema-level grants:

- `EDGARTOOLS_PROD_LOADER` — no grant on this schema
- `EDGARTOOLS_PROD_DEPLOYER` — no grant on this schema

`03_dashboard_contract.sql` would also `GRANT SELECT ON VIEW` for six named
views to `{{ reader_role }}` and explicitly **not** grant the publication
table. Those named GRANTs were never applied because the SQL was never run.
Terraform's future-VIEW SELECT is the live equivalent for views, and it
likewise does **not** grant SELECT on tables. If
`DECISION_CONTRACT_PUBLICATION` were created tomorrow, `EDGARTOOLS_PROD_READER`
would still not be able to SELECT it without a new table grant.

No current views exist, so "which roles can SELECT the contract schema"
today is: USAGE-capable reader/dashboard_owner/SYSADMIN plus ACCOUNTADMIN
ownership — and there is nothing in the schema to SELECT.

---

## How live prod differs from the in-repo sketches

| Concern | In-repo sketch | Live prod 2026-09-10 |
| --- | --- | --- |
| Schema | `CREATE SCHEMA IF NOT EXISTS` in all three sketch files | Exists; created by `15_decision_schema.sql`, not the sketches |
| Publication table + READY rows | `DECISION_CONTRACT_PUBLICATION` with `PUBLICATION_STATUS` | Table absent; no READY count |
| Feature screen | `SUBJECT_FEATURE_SCREEN` over MDM-active | View absent; underlying `MDM_COMPANY_ENTITY` + `FINANCIAL_FACTORS` exist |
| Issuer bundle | `02` = `BUNDLE_*` views; `03` = fail-closed `SUBJECT_BUNDLE_READ_ISSUER` | Both absent |
| Graph pointer | `03` joins `GRAPH_ACTIVE_POINTER` `POINTER_ID='active'` | Pointer exists and is `active` → `a573ebba-5820-49f2-8c40-43a4f538a79b` |
| Universe | `01` MDM-active; `03` gold `COMPANY` tracking-active | Both predicates currently yield the same 63,197 CIKs |
| Reader grants | `03` named VIEW GRANTs | Terraform USAGE + FUTURE VIEW SELECT on `EDGARTOOLS_PROD_READER` only |

Apply records: `deploy-snowflake-stack.sh` applies `15_decision_schema.sql`
then Snowflake access Terraform. Neither `install.sh` nor
`deploy-snowflake-stack.sh` references `infra/snowflake/sql/decision_contract/*.sql`.
That matches the empty live schema.

---

## Queries run this session

All against `--connection edgartools-prod`, `--format json` except the
initial identity `SELECT` and the three failing object `SELECT`s.

1. `SELECT CURRENT_ACCOUNT_NAME(), CURRENT_ORGANIZATION_NAME(), CURRENT_DATABASE(), CURRENT_ROLE(), CURRENT_WAREHOUSE();`
2. `SHOW SCHEMAS LIKE 'EDGARTOOLS_DECISION' IN DATABASE EDGARTOOLS_PROD;`
3. `SELECT ... FROM EDGARTOOLS_PROD.INFORMATION_SCHEMA.SCHEMATA`
4. `SELECT ... FROM EDGARTOOLS_PROD.INFORMATION_SCHEMA.TABLES` (decision/graph/gold/mdm names)
5. `SHOW OBJECTS IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_DECISION;`
6. `SELECT POINTER_ID, ACTIVE_GENERATION_ID, ACTIVATED_AT FROM ...GRAPH_ACTIVE_POINTER;`
7. `SELECT ... FROM ...GRAPH_GENERATION WHERE GENERATION_ID = 'a573ebba-...'`
8. `SELECT STATUS, COUNT(*), MAX(CREATED_AT), MAX(ACTIVATED_AT) FROM ...GRAPH_GENERATION GROUP BY STATUS;`
9. `SELECT COLUMN_NAME, DATA_TYPE, ... FROM INFORMATION_SCHEMA.COLUMNS` for `COMPANY` / `MDM_COMPANY_ENTITY`
10. `GROUP BY TRACKING_STATUS` counts on both tables
11. Active MDM CIK completeness; `COMPANY` entity-id coverage
12. Both active-set anti-joins
13. `SHOW GRANTS ON SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_DECISION;`
14. `SHOW FUTURE GRANTS IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_DECISION;`
15. `SHOW GRANTS OF ROLE EDGARTOOLS_PROD_READER;`
16. Failing `SELECT COUNT(*)` on `DECISION_CONTRACT_PUBLICATION`, `SUBJECT_FEATURE_SCREEN`, `SUBJECT_BUNDLE_READ_ISSUER`
17. Name search for sketched objects plus `SEC_AUDITOR_REPORT_EVIDENCE`
18. Gold object types for `COMPANY` / `MDM_COMPANY_ENTITY` / `FINANCIAL_FACTORS` / `INSTITUTIONAL_HOLDINGS`
