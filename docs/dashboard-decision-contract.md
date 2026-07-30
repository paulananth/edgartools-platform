# Dashboard Decision Contract publication

Agent View is a fail-closed audit surface over versioned objects in
`EDGARTOOLS_DECISION`. It never searches or renders identity from unrestricted
gold tables.

## Apply the contract objects

Use the SnowCLI connection with DDL rights for the target environment:

```bash
export SNOW_CONNECTION=snowconn

snow sql --connection "$SNOW_CONNECTION" \
  -f infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql \
  -D database=EDGARTOOLS_DEV

snow sql --connection "$SNOW_CONNECTION" \
  -f infra/snowflake/sql/decision_contract/03_dashboard_contract.sql \
  -D database=EDGARTOOLS_DEV \
  -D reader_role=EDGARTOOLS_DEV_READER
```

The SQL creates a private publication ledger plus three public views:

- `DECISION_CONTRACT_STATUS`
- `SUBJECT_BUNDLE_READ`
- `SUBJECT_BUNDLE_READ_ISSUER`

The reader role receives only the public views. It cannot read the publication
ledger or raw graph tables through these grants.

## Publish a verified watermark

Publication is an operator assertion made only after the warehouse full-chain
and integrity evidence has passed and `mdm verify-graph` has passed for the
same active graph generation. Insert a new immutable row; never update an old
watermark to make it appear current.

```sql
INSERT INTO EDGARTOOLS_DEV.EDGARTOOLS_DECISION.DECISION_CONTRACT_PUBLICATION (
  DECISION_WATERMARK,
  DECISION_CONTRACT_VERSION,
  BUSINESS_DATE,
  GOLD_UPDATED_AT,
  GRAPH_GENERATION_ID,
  COVERAGE_STATE,
  ALIGNMENT_STATUS,
  PUBLICATION_STATUS
)
SELECT
  '<release-data-watermark>',
  '1',
  '<business-date>'::DATE,
  '<verified-gold-updated-at>'::TIMESTAMP_TZ,
  ACTIVE_GENERATION_ID,
  '<complete-or-partial>',
  'aligned',
  'ready'
FROM EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER
WHERE POINTER_ID = 'active';
```

Agent View returns no subject rows unless the newest ready publication still
matches the one active graph pointer. A generation activation or rollback
therefore invalidates the prior publication automatically. Republish only
after the new generation and gold watermark have been independently verified.

Explore mode remains visibly marked “not for agent” and may query broader gold
read models for human research.
