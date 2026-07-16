# Define the Release Evidence Manifest

Type: grilling
Status: resolved
Blocked by:

## Question

What exact manifest must bind the immutable Release Candidate commit, warehouse and MDM image digests, release watermark, gate evidence, operator approvals, timestamps, and secret-safe provenance so every later gate refers to one authoritative release identity?

## Answer

Use one append-only Candidate Evidence Set per Release Candidate at
`docs/release-readiness/releases/rc-<YYYYMMDD>-<12-char-commit>/`, containing
`release-evidence.json` and a secret-safe `evidence/` directory.

The manifest is the authoritative index and records:

- schema version, candidate ID, full integration commit SHA, source branch, lifecycle status, and identity-freeze timestamp;
- exact warehouse and MDM `sha256:` image digests without registry or account identifiers;
- a composite Release Data Watermark spanning the bronze input-manifest digest and maximum eligible business date, bounded full-chain execution identity/scope, silver shard-manifest digest, Snowflake export run/business date/manifest digest, MDM publication watermark, and hosted-graph generation/publication identity;
- every required gate's status, repository-relative evidence paths, evidence SHA-256 digests, media types, capture tool/version, capture/expiry timestamps, and sanitization result;
- structured Gate Attestations containing role, stable approver handle, UTC timestamp, candidate identity, watermark digest, and evidence digest;
- final `go`, `no_go`, or `superseded` disposition, Release Owner attestation, expected Release Seal tag, and addendum references.

Candidate identity freezes when the first production validation gate starts. Any commit or image-digest change creates a new candidate. Failed and superseded candidates remain committed permanently. Finalized records are immutable; corrections use a signed addendum or new candidate. Live production evidence must share one Release Data Watermark and remain within the 24-hour Live-Evidence Window.

The manifest indexes digest-bound sanitized artifacts rather than embedding raw output. Raw logs, generated AWS application JSON, ARNs, account identifiers, DSNs, credentials, and connector traces remain outside Git.

Candidate Builder, AWS Operator, Snowflake Operator, MDM/Graph Operator, Dashboard Reviewer, and Release Owner are logical roles. One person may hold multiple roles, but each gate requires a distinct attestation and final GO is a separate Release Owner action.

Release Evidence Automation must generate the manifest deterministically, append sanitized gate metadata, validate schema and lineage, scan for secrets, enforce freshness and identity freeze, and reject incomplete gates. It must never manufacture human approval. Final GO requires a verified signed annotated Git tag on the evidence commit.
