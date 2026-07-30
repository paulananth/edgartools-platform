# Design the Release Evidence Automation

Type: prototype
Status: resolved
Blocked by: 01

## Question

What concrete CLI, JSON schema, state-transition model, sanitization boundary, and validation report should deterministically create and maintain Candidate Evidence Sets while reserving Gate Attestations and the Release Seal for humans?

## Answer

Implemented as working code (per an explicit `/implement` request, not the throwaway-prototype
default this ticket's type would otherwise imply): `edgar_warehouse/application/release_evidence.py`
(pure logic, no network/AWS/Snowflake I/O, no wall-clock reads) plus a thin argparse CLI wrapper,
`edgar_warehouse/scripts/release_evidence_cli.py` (`init` / `add-gate` / `validate`), following this
repo's existing `edgar_warehouse/scripts/*.py` convention (e.g. `build_ticket20_strict_execution_input.py`).

**Schema** (`release-evidence.json`, `schema_version: 1`): candidate identity (`candidate_id`,
`commit_sha`, `source_branch`, `lifecycle_status`, `identity_freeze_timestamp`), bare
`sha256:<64-hex>` image digests (no registry/account), an opaque-but-schema-validated
`release_data_watermark` (8 required top-level sub-fields per ticket 01's Answer, plus nested
`snowflake_export`/`hosted_graph` sub-schemas), an append-only `gates` array (10 required fields
per gate, including a `sanitization` record), `attestations` (6 required fields per record when
present), and reserved-for-humans `disposition` (enum `go`/`no_go`/`superseded`/null),
`release_owner_attestation`, `release_seal`, `addendum_references` — all left null/empty by every
code path in the module.

**State-transition model:** `init` opens a candidate and freezes identity. A byte-identical
re-init (e.g. a retried deploy step) is an idempotent no-op; a re-init with the same
`candidate_id` (same commit + date) but different content (e.g. a changed image digest) is
rejected outright — per ticket 01, "Any commit or image-digest change creates a new candidate,"
so this collision must fail loudly, not silently merge. `add-gate` is append-only (rejects
duplicate gate names) and refuses once `disposition` is non-null (no further gates after a final
disposition). Only `init`/`add-gate` write; `validate` never mutates its input.

**Sanitization boundary:** `scan_for_secrets` fails closed on 12-digit AWS account IDs, `arn:aws:`
prefixes, ECR registry hosts, Postgres/Snowflake DSNs, and Snowflake account-locator-shaped
strings. `add-gate` refuses to record any gate whose evidence content matches (evidence must be
clean *before* it enters the manifest); `validate` independently re-scans on-disk evidence as a
defense-in-depth check against post-hoc tampering.

**Validation report:** schema (required fields, gate/attestation/watermark completeness,
disposition enum, image-digest format), lineage (candidate_id-vs-commit_sha tail match,
evidence-path-under-this-candidate's-own-evidence-dir), digest drift (recorded vs. on-disk
sha256), freshness (fixed 24-hour Live-Evidence Window per ticket 01 — not an operator-adjustable
flag), and secrets — emitted as a structured `{ok, findings: [{code, message, gate_name}]}` JSON
report, printed to stdout and optionally written to a file.

**Explicitly out of scope** (per the scoping decision made before writing code): producing any
gate's own evidence content, querying AWS/Snowflake/MDM to compute a live watermark, writing Gate
Attestations or a final disposition, creating the Git Release Seal, and retrofitting the existing
flat `docs/release-readiness/*.json` evidence files into the new `releases/rc-.../` layout — the
manifest indexes artifacts, it never collects them.

**Verification:** TDD throughout (137 focused tests: 114 pure-module, 17 CLI, 6 architecture, plus a
dedicated architecture test asserting the module can never manufacture human approval — statically
grepping for forbidden disposition-assignment literals and function names, plus behaviorally
confirming every code path leaves `disposition`/`attestations`/`release_seal` untouched). Two-axis
`/code-review` run against ticket 01's Answer as spec: found and fixed one Standards-axis hard
violation (CLI raw tracebacks on malformed input instead of the repo's clean stderr+exit-code
pattern) and four Spec-axis gaps (missing `addendum_references`/`release_owner_attestation`
fields, unvalidated disposition enum, unvalidated attestation/watermark shape, and an
operator-configurable `expiry_hours` that undercut the fixed 24-hour invariant) — all fixed and
covered by new tests before commit.

Successive post-handoff adversarial reviews found and closed fail-closed gaps covering fabricated
GO manifests, schema/lifecycle/gate/watermark/expiry tampering, malformed JSON types, identity and
timestamp chronology, candidate/evidence/CLI directory lineage, symlink escapes, and
Postgres/Snowflake DSN leakage. Until ticket 08 defines the complete gate inventory and signer
sequence, GO validation returns `go_validation_not_implemented` rather than manufacturing an
approval predicate. Final independent review: APPROVE. Focused verification: 137 passed with 93%
statement coverage across the module and CLI. Repository-wide verification: 1519 passed, 4
skipped, 35 subtests passed, with 3 pre-existing MDM test-double failures in
`tests/mdm/test_cli_snowflake_graph.py`; their fix is outside this branch's explicitly selected
two-commit handoff scope.
