# Verify Snowflake, OpenMetadata, and AutoOntology parity

Status: open
Owner: Claude (operator, 2026-11-17: "take over Unresolved integration and safety gaps remain documented in docs/handoff-connectivity-claude.md"; the handoff's findings are the parts below).
Type: task

## Question

Implement a deterministic parity check across the approved exposure manifest, Snowflake metadata, OpenMetadata assets, and AutoOntology catalog/semantic compilation after `Connect AutoOntology to the approved Snowflake surface` and `Publish the approved Snowflake surface to OpenMetadata` complete.

Acceptance criteria:

- Missing, extra, renamed, or differently typed assets are reported separately.
- Business-description and authority drift is reported separately from physical-schema drift.
- Lineage and certification mismatches fail the check where the manifest requires them.
- The check uses invented or approved test metadata only and never prints credentials or source records.
- Output identifies the owning system and remediation path for every mismatch.

Blocked by: 02, 03

## Checklist

- [x] Moved unchanged to `skills/data-platform/scripts/exposure/exposure_parity.py` (2026-11-17 19:59 ET)
- [ ] Reference-form lineage is ignored (missing lineage passes, present lineage is called extra): compare the manifest's lineage form
- [ ] Certification, and AutoOntology readiness and scope, checked
- [ ] A strict snapshot schema, per-system ownership, duplicate identities, a stated type-equivalence policy, and a snapshot bound to its manifest (stale refused)
- [ ] A rename is missing plus extra; no rename inferred without a stable identity
- [ ] Glossary comparison stated (none while the manifest names no terms)
- [ ] Negative tests for each mismatch kind, asserting its owner and the failed status
- [ ] ~~The Snowflake side~~ deferred to the mirror's qualification; compare the PostgreSQL stores meanwhile
- [ ] Learning → skill
