# MdmExport Failure Boundary

## Conclusion

The July 5 production `MdmExport` failure was an external Snowflake entitlement
failure at connection authentication. The deployed task reached Snowflake, but
Snowflake rejected the connection because the target account's trial had ended
and its warehouses were suspended. The failure happened before export SQL,
row transformation, temporary-table creation, `MERGE`, or exported-row
acknowledgement.

This finding closes the historical failure classification. It does **not** prove
that the current production export path is ready.

## Observed failure boundary

- The production full-chain execution reached `MdmExport` only after
  `BatchSilver`, `MdmRun`, and `MdmBackfill` succeeded.
- `MdmExport` made four ECS attempts: the initial attempt plus three retries.
- Every attempt used the same deployed MDM task definition and image and exited
  with the same Snowflake connector `DatabaseError` within seconds.
- The stack stopped in `SnowflakeConnectionSettings.connect()` while
  `SnowflakeConnectorWriter.from_env()` was being constructed.
- No export query or MDM row write had started.

The repeated attempts therefore crossed the AWS-to-Snowflake network and secret
loading boundaries, but did not cross the Snowflake-authentication-to-export-SQL
boundary.

## Failure classes excluded by the evidence

- `MaxConcurrency=4` and BatchSilver write contention: BatchSilver had already
  completed 603 of 603 child items.
- MDM export transformation, table shape, or `MERGE` behavior: no export SQL ran.
- Missing Snowflake settings: the connector reached the configured account and
  received a specific account-state response.
- Generic network reachability: Snowflake returned an authenticated service
  response.
- A transient error made healthy by retry: all four attempts failed identically,
  while the current state machine retries every `States.TaskFailed` error.

## Current readiness status

The production MDM Snowflake secret received a new `AWSCURRENT` version on July
6, after the failed execution. Secret metadata does not reveal whether that
version targets the canonical paid production account, whether its warehouse is
runnable, or whether the deployed task role can execute the required export.
The local `snowconn` connection succeeds, but repository guidance identifies it
as the development-account administrative connection, so it cannot validate the
production runtime secret.

Current production `MdmExport` readiness is therefore **unverified**, not failed
and not passed.

## Architectural boundary

`MdmExport` cannot be waived from a Full-Chain Launch Pass. It publishes current
MDM golden records to the Snowflake MDM mirror that downstream graph sync reads.
Bypassing it would permit a successful workflow with stale graph inputs.

Running `mdm export` merely to test connectivity is also unsafe: after connecting
it can process pending change-log rows and mark them exported. A readiness check
must use a dedicated read-only command in the deployed MDM task context.

## Decision exposed

Before a Full-Chain Launch Pass can be specified, the project must define:

1. a secret-safe, read-only preflight that proves the deployed production task
   can connect to the canonical Snowflake target and execute with the expected
   database, schema, role, and runnable warehouse;
2. evidence fields that prove target identity without recording account locators,
   hostnames, credentials, or raw connector traces in Git;
3. which connector failures are non-retryable prerequisite failures that stop
   immediately, and which are transient failures eligible for bounded retry;
4. the operator remediation and revalidation sequence after secret rotation,
   entitlement restoration, or warehouse correction.

That decision is tracked separately as **Define the MdmExport Entitlement
Preflight and Retry Policy**.

## Evidence sources

This conclusion was derived using read-only inspection of the production Step
Functions execution history, the four referenced ECS task definitions and
CloudWatch log streams, production secret metadata (not its value), the current
state-machine definition, and the repository's MDM export and deployment code.
No secret value was read, no task was launched, and no production state was
changed.
