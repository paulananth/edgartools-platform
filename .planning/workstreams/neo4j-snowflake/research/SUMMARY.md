# Research Summary: Neo4j Graph Analytics Native App For Snowflake

workstream: neo4j-snowflake
updated: 2026-05-25

---

## Verified Assumptions

- Neo4j Graph Analytics for Snowflake is a Snowflake Native App installed through Snowflake Marketplace.
- The app is designed to operate on data already in Snowflake tables/views.
- The app runs inside Snowflake using Snowpark Container Services rather than an external Neo4j Aura/Bolt endpoint.
- The app supports creating graph projections from node and relationship tables and can write algorithm outputs back into Snowflake tables.
- Snowflake grants must give the application access to the relevant database/schema/table/view resources.

## Milestone Implications

- Treat this as a graph projection and validation migration, not a simple endpoint URL swap.
- `edgar-warehouse mdm sync-graph` should materialize Snowflake graph-ready tables/views and invoke or validate the Native App path through Snowflake context.
- External `NEO4J_*` credentials should be removed from milestone verification and replaced with Snowflake role/application configuration.
- Verification must include Snowflake table/view parity plus Native App query/projection checks.

## Sources

- Neo4j developer guide: https://neo4j.com/developer/snowflake-analytics/
- Neo4j docs: https://neo4j.com/docs/snowflake-graph-analytics/current/getting-started/
- Snowflake developer guide: https://www.snowflake.com/en/developers/guides/practical-graph-analytics-neo4j-snowflake/
- Snowflake Marketplace listing: https://app.snowflake.com/marketplace/listing/GZTDZH40CN
