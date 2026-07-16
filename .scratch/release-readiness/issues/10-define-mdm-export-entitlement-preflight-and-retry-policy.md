# Define the MdmExport Entitlement Preflight and Retry Policy

Type: grilling
Status: resolved
Blocked by: 02

## Question

What dedicated read-only check must prove that the deployed production MDM task can use its runtime secret to reach the canonical active Snowflake target with the expected role, database, schema, and runnable warehouse; what secret-safe evidence must it emit; and which Snowflake connector failures must fail fast rather than consume the generic `States.TaskFailed` retry policy?

## Answer

Add a mandatory, independently runnable `MdmExportPreflight` immediately before
every `MdmExport`, using the same deployed MDM image, task definition, role,
network, and injected secret. It passes only when an independently pinned
Production Target Marker matches; the role, database, schema, and warehouse
match; a warehouse-backed read succeeds; all five export targets are compatible;
and the runtime role has every effective privilege required by the export.

The preflight emits deterministic, candidate-bound, secret-safe JSON with
per-check results, runtime and secret-version fingerprints, sanitized structured
failure data, freshness, and sanitization metadata. Raw infrastructure and
connector details stay outside Git.

Remove the blanket Step Functions retry from both the preflight and export. The
MDM command owns at most three total attempts and retries only explicitly
classified transient connectivity, service, throttling, warehouse-resume, and
session/statement failures. Configuration, authentication, entitlement,
identity, context, schema, privilege, TLS, resource-monitor, and unknown failures
fail immediately.

After a non-retryable failure, an authorized operator corrects the prerequisite,
runs a fresh independent preflight, and then starts a fresh full-chain execution.
There is no automatic mutation or target fallback. Candidate Builder owns the
implementation contract, with Snowflake Operator and AWS Operator contributions;
no named human implementer is assigned yet.

Full policy:
[MdmExport Entitlement Preflight and Retry Policy](../../../docs/release-readiness/mdm-export-entitlement-preflight-policy.md)
