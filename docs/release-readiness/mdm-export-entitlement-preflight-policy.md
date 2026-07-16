# MdmExport Entitlement Preflight and Retry Policy

## Decision

Every workflow containing `MdmExport` must run a mandatory, fail-closed
`MdmExportPreflight` state immediately before it. Operators may invoke the same
preflight independently. It must use the same MDM image, ECS task-definition
family, task role, network path, and injected Snowflake secret as `MdmExport`.

A developer or administrative Snowflake connection is not substitute evidence.
The preflight must never call `mdm export`, write a test row, change a warehouse,
rotate a secret, grant a privilege, or fall back to a different target.

## Required checks

One preflight passes only when all of these checks pass:

1. Load the injected production Snowflake secret and establish a connection.
2. Read the canonical account's opaque Production Target Marker and match it to
   the value pinned in the Release Evidence Manifest.
3. Match the active role, database, schema, and warehouse to the manifest's
   expected production context.
4. Complete a warehouse-backed read, proving that the warehouse is runnable and
   not merely named in the session.
5. Confirm that `MDM_COMPANY`, `MDM_ADVISER`, `MDM_PERSON`, `MDM_SECURITY`, and
   `MDM_FUND` exist with schemas compatible with the current exporter contract.
6. Confirm the runtime role's effective grants cover database, schema, and
   warehouse usage; temporary-table creation; and the target-table operations
   required by `MERGE`.

The checks are non-mutating. The subsequent `MdmExport` remains the proof that
the write path actually executes.

## Evidence contract

The command emits versioned, deterministic JSON for the Candidate Evidence Set.
It contains:

- Release Candidate identity and exact MDM image digest;
- sanitized ECS task-definition family and revision;
- a SHA-256 fingerprint of the injected secret version;
- a SHA-256 fingerprint and match result for the Production Target Marker;
- separate PASS/FAIL results for connection, execution context, warehouse-backed
  query, each target schema, and each required effective privilege;
- sanitized failure disposition, internal failure class, numeric Snowflake error
  code, and SQLSTATE when available;
- a SHA-256 fingerprint of each relevant Snowflake query identifier;
- UTC start/end timestamps, expiry timestamp, command version, evidence-schema
  version, and sanitization result.

Raw hostnames, account identifiers, account locators, secret names and values,
ARNs, SQL text, raw query identifiers, connector messages, and connector traces
must not enter Git.

## Retry policy

Step Functions must not apply a blanket `States.TaskFailed` retry to
`MdmExportPreflight` or `MdmExport`. The MDM command owns classification and a
maximum of three total attempts with jittered backoff.

Only `transient_retryable` failures may consume that budget:

- connection timeout, reset, or temporary DNS failure;
- Snowflake service unavailability or throttling;
- temporary warehouse resume/provisioning state;
- explicitly classified transient session or statement failure.

The following are `operator_action_required` and fail immediately:

- missing or malformed configuration;
- authentication or credential-policy rejection;
- expired, disabled, trial-ended, or billing-suspended account;
- Production Target Marker mismatch;
- role, database, schema, or warehouse mismatch;
- missing or incompatible export target;
- missing effective privilege or exhausted resource monitor;
- TLS or certificate-validation failure.

Every unclassified failure is `unknown_fail_closed` and fails immediately.
Classification must use structured exception attributes and internal codes, not
raw message-string matching.

## Remediation and revalidation

An `operator_action_required` or `unknown_fail_closed` result stops the workflow
before export. The failed evidence remains in the Candidate Evidence Set. The
preflight performs no automatic remediation.

An authorized AWS or Snowflake operator corrects the prerequisite through the
approved secret, access, or provisioning path. The operator then runs the
independent preflight using the same candidate image and deployed runtime
boundary. After it passes, release validation starts a fresh full-chain
execution; it does not resume at `MdmExport`.

A code or image change creates a new Release Candidate. A secret-only correction
may retain the candidate identity, but the new secret-version fingerprint
invalidates prior live evidence and requires a fresh Candidate Evidence Set gate
run within the Live-Evidence Window.

## Ownership

- **Candidate Builder** — accountable for the preflight command, structured
  classification, evidence schema, and automated tests.
- **Snowflake Operator** — responsible for the Production Target Marker, export
  target contract, effective grants, and Snowflake-side remediation.
- **AWS Operator** — responsible for state-machine placement, removal of blanket
  retries, runtime-bound invocation, and evidence capture.
- **Release Owner** — accepts the gate contract and its PASS evidence for GO.

These are logical roles. A named human implementer has not yet been assigned.
