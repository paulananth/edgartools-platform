# Add Snowflake role passthrough to AutoOntology

Status: open
Owner: unassigned
Type: task

## Question

Update and release AutoOntology's structured Snowflake connection path so the configured `role` survives connection-string construction and reaches the Snowflake connector as its `role` connect argument. Add a regression test for the structured payload-to-connector path.

The operator selected upstream role passthrough for this map; using the Snowflake user's default role is not an acceptable workaround. The current release in use is `8ff3060`; its connection-string factory serializes warehouse and database but omits role, while the connector applies role only when present in the URL query.

Acceptance criteria:

- The structured Snowflake connection's configured role is included in the connection URL.
- A regression test proves the connector receives that role.
- The upstream release/revision containing the fix is identified for downstream pinning.
- This does not qualify downstream access by itself; the effective table-level grants and live approved-mirror query remain separate gates.

Blocked by: none
