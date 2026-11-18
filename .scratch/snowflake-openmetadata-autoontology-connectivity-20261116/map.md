# Snowflake, OpenMetadata, and AutoOntology connectivity

## Destination

Implement a governed connectivity path in which AutoOntology queries an approved Snowflake surface, while OpenMetadata and AutoOntology remain consistent through one generated exposure manifest.

## Notes

Domain: platform metadata and semantic query connectivity.

Authorities: repository rules own business definitions and approved scope; Snowflake owns physical tables and columns; OpenMetadata owns governance, glossary, certifications, and lineage; AutoOntology is a read-only semantic/query projection.

Execution is included in this map because the user explicitly requested implementation tickets. Keep production access and writes gated by credentials, target, and operator authorization. Use `aws-snowflake-operations`, `openmetadata`, `data-catalog`, `domain-modeling`, and `diagnosing-bugs` where applicable.

## Decisions so far

- The destination, authority split, and local-first deployment boundary were agreed in conversation before ticket creation.
- Scope (operator, 2026-11-17): "Silver, MDM and RDM", and "Published-only RDM tables (Recommended)": silver's 16 tables and MDM's two final tables now; RDM once it has published-only tables (ticket 06).
- Form (operator, 2026-11-17): "only skills and generic scripts": the code is `skills/data-platform/scripts/exposure/`.
- Reality: no Snowflake surface exists yet (the mirror `DB_EDGARTOOLS_MIRROR` is planned, not built). Snowflake-side proofs are deferred to its qualification; AutoOntology reads the PostgreSQL stores through read-only logins meanwhile (auto-ontology skill).

## Not yet specified

- Exact manifest schema and versioning rules.
- The approved Snowflake database/schema/table scope.
- How OpenMetadata lineage identities map to the manifest.
- How AutoOntology semantic compilation consumes approved descriptions and relationships.
- Production scheduling, credentials, network path, and drift-alert ownership.

## Out of scope

- Making AutoOntology a business-definition authority.
- Writing AutoOntology or OpenMetadata metadata back into Snowflake.
- Replacing the repository rules catalog publisher.
- Production deployment or credential provisioning in this planning effort.
