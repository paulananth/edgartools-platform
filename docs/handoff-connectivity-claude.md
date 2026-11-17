# Claude handoff: Snowflake, OpenMetadata, AutoOntology connectivity

## State and destination

Branch: `codex/autoontology-snowflake-20261116`. Implementation head before this handoff: `6b9ac12ddfe844451cc8e6ea7a4eaffc493580e3`.

This is unfinished work, not a validated integration. Keep the PR draft. Earlier completion claims were overstated; passing invented-input tests did not establish the service contracts or operational safety.

User-approved destination: AutoOntology queries an approved Snowflake surface; one generated exposure manifest keeps its scope consistent with OpenMetadata. Repository rules own business definitions and approved scope; Snowflake owns physical metadata; OpenMetadata is the governance/catalog projection; AutoOntology is a read-only semantic/query projection. Local-first; no production deployment was authorized by the ticket work.

The local tracker is `.scratch/snowflake-openmetadata-autoontology-connectivity-20261116/` in the original checkout. It is not part of these implementation commits. Five tickets exist; there is no ticket 06. Requirements and remaining work follow so this handoff is usable from the PR alone.

## Code and requirements

- `edgar_warehouse/rules/exposure_manifest.py`: ticket 01, deterministic versioned artifact generated from rules; physical identities, columns, business authority, descriptions, lineage, approved scope, digest and compatibility validation.
- `edgar_warehouse/integrations/autoontology.py`: ticket 02, secret-backed read-only connection, bounded ingestion, semantic compilation and generated SQL/row verification.
- `edgar_warehouse/rules/exposure_publish.py`: ticket 03, idempotent manifest-owned OpenMetadata publication and native metadata/lineage readback.
- `edgar_warehouse/rules/exposure_parity.py`: ticket 04, deterministic cross-system physical/business/lineage/certification drift, with owner and remediation.
- `edgar_warehouse/rules/exposure_operations.py` and `docs/exposure-connectivity-operations.md`: ticket 05, executable local workflow, exact production authorization, bounded failures, cadence, ownership, rollback and staleness.
- Matching tests are `tests/unit/test_exposure_{manifest,publish,parity,operations}.py` and `tests/unit/test_autoontology_connection.py`.

## Remaining review findings

### Manifest prerequisite

The builder accepts caller-created mappings, not actual repository-rule generation. There is no reviewed exposure configuration/artifact. Hardcoded database/schema scope is not generic approval. Validation verifies version and digest but not a complete strict consumer schema or freshness. Do not treat a valid digest as authorization. Resolve approved physical scope from current configuration; do not assume schema membership authorizes every table. Earlier reviewers disputed production database names; verify current evidence rather than copying either assertion.

### AutoOntology

A `_READER` suffix does not prove grants. The upstream structured Snowflake factory inspected during this session drops `role`, so adding it to the payload does not enforce role selection. Unqualified table regex across several schemas can admit unwanted name collisions. Scheduled ingestion can prefer `CONNECTION_STRINGS` over filtered UI connections; fail closed and read actual ingested identities back. `calculated` alone is not compilation success. `validate_query` accepts supplied event strings but its live path raises an unimplemented-streaming-client error. Implement actual supported SSE query validation; do not count an invented response as service proof. URL credentials need correct decoding and safe exception handling. The new integrations package was not wired into bundle-wheel packaging. Check upstream contracts before changes; do not commit to another repository.

### OpenMetadata

Reuses `catalog.publish` / `catalog.verify`, but glossary term identity is absent from the manifest; do not invent glossary words from `mdm` or other authority labels. Consumer exposure eligibility is distinct from certification and data class. Unknown authority is silently dropped; source and silver collapse to one tag; old authority tags remain. Shared `data_class` writes exceed manifest-owned scope. Physical identities are joined/split on dots, breaking quoted names. Column types are forwarded without catalog translation. Reference membership is not evidence that lineage is verified. Repeated certification patches change timestamps; idempotency needs a stated semantic contract and proof. The custom fake has generic handlers before lineage-specific handlers and can agree with its own invented contract; replace weak tests with supported contract evidence and behavior assertions.

### Parity

Reference-form manifest lineage is ignored: missing approved lineage can pass, while present lineage is called extra. No certification or AutoOntology readiness/scope checks. No strict snapshot schema, per-system ownership normalization, duplicate identity handling, explicit type-equivalence policy, or stale snapshot/manifest binding. Rename currently means missing plus extra; do not infer a rename without stable identity. Clarify glossary comparison. Tests miss several negative cases and do not reliably assert owner or failed status.

### Operations

Approval and cadence are unused labels, not enforced gates. Callbacks returning `ok: false` can still produce a success receipt. Side effects run before parity, with no compensation on failure. No callback deadlines or concrete executable orchestration/scheduler. Exceptions can carry secrets through chained causes; drift failure discards useful kind/owner/remediation. Caller-supplied creation time permits stale-check bypass and naive dates are accepted. Rollback to an old passing digest conflicts with a 24-hour expiry; specify replay versus freshness. The runbook's production role, scope and target require verification; no warehouse is selected. Local verification is a Python snippet with undefined inputs, not a runnable fixture workflow. Fix tests that pin internal order or claim redaction without injecting a secret; cover future dates and callback exceptions.

## Verification actually observed

- Connectivity tests before operations: 13 passed in 0.08 seconds.
- Operations plus parity: 6 passed in 0.05 seconds.
- Python compileall was used; it is syntax compilation, not typechecking.
- Broader earlier catalog run: 78 passed, 3 failed due to missing `sqlalchemy`; not repaired by changing catalog code.
- No full-suite result, deployed service contract proof, live Snowflake query, or live OpenMetadata/AutoOntology integration proof was obtained for these commits.

Use repository testmon commands and affected tests under the local five-minute limit; CI runs the full suites. Read CLAUDE.md, relevant skills, current package configuration and current contracts before editing. Review Standards, Spec and GoF after fixes. Do not repeat a failed check merely to confirm a known failure.

## Safety and next action

Do not run the current production workflow. Do not rotate credentials, grant privileges, publish catalogs, connect platform stores, or trigger production loads from this handoff. Preserve unrelated worktrees/edits. Keep credentials, DSNs, host values and source records out of output. Invented metadata only in public Git history.

Start by repairing the manifest/approval contract and proving the real API shapes; then fix dependent integration paths. Resolve review findings rather than adding another wrapper around incomplete helpers. Update ticket status only after acceptance proof. Keep PR draft until implementation, tests, packaging and review are complete.
