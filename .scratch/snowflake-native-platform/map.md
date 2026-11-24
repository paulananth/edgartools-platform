# Map: the platform in a box, inside Snowflake

## Destination

An additional deployment target, not a replacement: the whole platform (load,
MDM, silver, gold, catalog, ontology, monitoring) can run inside one Snowflake
account, with no internet hop between the parts, so the platform is
multi-platform and an AI-native data platform in a box. Today's targets (the
local Docker load pipeline, AWS Step Functions, OpenMetadata, AutoOntology)
stay as they are.

## Notes

- Operator, 2026-11-24 17:18 ET: "Create a research ticket if I need to run the entire set up in Snowflake, with no internet latency using snowflake container service and Snowflake Horizon Catalog and business ontology removing the need for autoontology and open metadata. This will be an additional architecture don't remove anything we are making it multi-platform and AI native data platform in a box."
- Additive only: no existing skill, rule, store or pipeline is removed by this map.
- Provider access (SEC, GLEIF, OpenFIGI) keeps its existing authorization; the research reads Snowflake documentation only.
- Skills to consult: aws-snowflake-operations, data-catalog, openmetadata, data-operations, mdm-engineering.

## Decisions so far

(none yet)

## Not yet specified

- Which of the four platform duties (load, MDM, silver and gold, catalog and ontology) move first.
- The cost of an always-on container service against today's load windows.

## Out of scope

- Removing OpenMetadata, AutoOntology, the local pipeline or AWS (the operator ruled them additive).
