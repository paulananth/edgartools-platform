Type: grilling
Status: resolved
Blocked by: 03
Labels: `wayfinder:grilling`

## Checklist

- [x] Reuse the existing native test cases for each configured MDM check and map results to their source assets. 2026-11-13 21:39 ET
- [x] Publish complete and incomplete MDM run outcomes with exact timestamped readback and replay safety. 2026-11-13 21:39 ET
- [x] Record the approved OpenMetadata projection and incomplete-evidence contract in this ticket. 2026-11-13 21:39 ET
- [x] Validate 246 Company, Person, Security, Bookkeeping, and catalog tests; 171 focused tests after projection fixes; and 98 focused tests after the stable run-history timestamp fix. Syntax and `git diff --check` pass. CI remains outstanding. The wider MDM folder run was stopped at its five-minute cap. 2026-11-13 21:56 ET
- [x] Learning → skill: update the shared OpenMetadata result-history instructions for `Aborted` and exact readback. 2026-11-13 21:39 ET

# Decide OpenMetadata Projection and Readback for MDM Quality

## Question

How should Bookkeeping-admitted MDM outcomes map to the existing OpenMetadata
test cases and per-load result history?

Specify the stable mapping from an admitted check to its catalog test case,
including the source asset or master table it describes; which per-run status,
counts, failure action, and rule version are published; how exact timestamped
readback proves the result; and how replay avoids duplicate or synthetic
results. Reuse the shipped API/UI and the verified Silver publication path;
OpenMetadata remains the results viewer, not the execution engine.

The answer should identify the specific check/readback proof needed for
Company, Person, and Security and explain how incomplete evidence remains
visibly unconfirmed.

## Answer

Operator-approved projection: OpenMetadata is the sole user-facing discovery
and result surface. MDM executes checks; Bookkeeping retains and admits their
receipts. Reuse the `source.yaml`/`quality.yaml`-generated test cases already
present in the catalog plan; do not create entity-specific cases or duplicate
the check configuration.

- Map an admitted check to the existing test case named
  `<source-contract-code>.<check-id>` on that source's catalog table asset.
  The source contract code is also the receipt's `table` field, so the current
  catalog naming convention resolves the asset and case without an entity
  adapter.
- Publish `rows_checked`, `rows_failed`, the configured failure action, the
  quality rule version in result detail, observation/load correlation, and a
  status derived only from admitted evidence. Bookkeeping keeps its immutable
  per-unit evidence; OpenMetadata receives one stable aggregate per source
  check and run, with counts summed only from verified unit receipts and the
  immutable Bookkeeping run creation time as its history timestamp. Per-unit
  observation times remain in result correlation. Re-publishing an incomplete
  run therefore updates the same history row as more units become verified.
  Complete outcomes map to
  `Success` or `Failed`. Incomplete evidence maps to `Aborted`; only verified
  counts are included and the detail states the unknown row/work-unit counts.
  An MDM target's missing receipt makes its check outcomes unknown because that
  step's declared source scope cannot be proven complete. Keep source scopes in
  target Rules; do not add entity/source branches. If a future target combines
  independent source scopes, extend its declared expected-scope evidence before
  enabling partial per-source outcomes.
- Preserve stable run/step/opaque-unit identity. On replay, an identical
  same-timestamp result is idempotent. A duplicate or mismatch is an error;
  duplicate MDM aggregate results for the same catalog case are refused rather
  than assigned synthetic timestamps. The publisher may perform one
  timestamp-specific correction and must then
  read back exactly one row matching timestamp, status, result text, row
  counts and values before confirming publication.
- If no work-unit evidence exists for a check, do not invent a zero-count
  result. Keep the run-level summary unknown and do not report a pass or fail.

### Examples

- Company: SEC company and GLEIF check ids map to their source contract table
  cases; each case result uses the relevant receipt's verified counts.
- Person: SEC submissions, SEC ownership and IAPD ADV checks use the same
  `<source-contract-code>.<check-id>` mapping.
- Security: N-PORT security and 13F security checks use that same mapping.

In every example, `rules catalog check --bookkeeping-run <run-id>` performs
read-only exact result-history readback; `rules catalog publish
--bookkeeping-run <run-id>` sends and verifies the result. OpenMetadata does
not execute these checks. Recovery qualification and enablement remain gated
by [Bookkeeping recovery](../../../skills/bookkeeping/RECOVERY.md); the new MDM
quality check is not enabled in production by this implementation.
