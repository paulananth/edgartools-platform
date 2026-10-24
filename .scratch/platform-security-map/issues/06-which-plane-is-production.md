# Which plane is the production read path until an export writer exists

Type: grilling
Status: open
Blocked by:

## Question

Workers land silver in PostgreSQL. Snowflake pulls an S3 export prefix, dbt builds gold, and Streamlit reads gold. A search of `edgar_warehouse` at `6a272d4d` found no writer of that prefix. Until a writer exists, which plane should a reader trust: PostgreSQL silver, or Snowflake gold?

## Checklist

- [ ] Grilling with the operator. Do not answer for them.
- [ ] Learning → skill: if the operator names the production read path, record it where agents look for pipeline shape.
