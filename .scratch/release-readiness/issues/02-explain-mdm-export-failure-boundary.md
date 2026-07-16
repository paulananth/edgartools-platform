# Explain the MdmExport Failure Boundary

Type: task
Status: resolved
Blocked by:

## Question

What read-only investigation must be completed to identify the production `MdmExport` failure class and determine which architectural or operational decision must be made before a Full-Chain Launch Pass is possible?

## Answer

The historical failure is classified as an external Snowflake entitlement
failure at connection authentication. The deployed task reached Snowflake, but
the target account rejected it because its trial had ended and its warehouses
were suspended. The failure occurred before export SQL or any exported-row
acknowledgement, excluding BatchSilver concurrency, MDM transformation, table
shape, and network reachability as causes.

The production secret changed after the incident, but metadata alone cannot
prove that its current value targets the canonical active production account.
The local working Snowflake connection is development-scoped and is not evidence
for the deployed production task. Current production export readiness remains
unverified.

`MdmExport` is required because graph sync consumes the Snowflake MDM mirror, and
the existing `mdm export` command is not a read-only connectivity test. The next
decision is therefore to define a dedicated deployed-runtime entitlement
preflight and classify fail-fast versus retryable connector errors.

Sanitized investigation record:
[MdmExport Failure Boundary](../../../docs/release-readiness/mdm-export-failure-boundary.md)
