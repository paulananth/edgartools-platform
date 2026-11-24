# 01: Can the whole platform run inside Snowflake, with no internet hop?

Status: open
Type: research
Blocked by: none

Operator, 2026-11-24 17:18 ET: "Create a research ticket if I need to run the entire set up in Snowflake, with no internet latency using snowflake container service and Snowflake Horizon Catalog and business ontology removing the need for autoontology and open metadata ... This will be an additional architecture don't remove anything we are making it multi-platform and AI native data platform in a box."

## Question

If the platform ran entirely inside one Snowflake account, what would it take,
what would it cost, and what would it not do? The answer is an additional
architecture beside the current ones; nothing existing is removed.

## What the research answers

Sources: Snowflake's own documentation only (no provider request). Each answer
cites the page, and says "measured" or "from the documentation".

1. **Compute (Snowpark Container Services).** Can the loader image (the one the
   CI builds, now run by the local Step Functions pipeline) run as a service or
   a job in a compute pool? Which pool sizes carry our measured load (about 0.4
   GiB a worker, the database-bound load, lanes and workers from one budget)?
   What replaces Step Functions' ordering, retries and lane budget: tasks,
   task graphs, job services, or the image's own activity worker?
2. **Databases.** The load needs PostgreSQL 16 for MDM, RDM, Rules, Bookkeeping,
   Change Journal and Silver. Does Snowflake Postgres satisfy the portable-SQL
   rule and the engine's adapter tests, and is it reachable from a container
   service with no public internet hop (private connectivity, network rules)?
3. **Provider access.** SEC, GLEIF and OpenFIGI are on the internet. Which
   external access integration and egress rule lets the service fetch only
   with the existing authorization, and what stays latency-bound? Where do
   captured files live (stage, external stage, volume mount)?
4. **Catalog.** What of OpenMetadata's duties does Snowflake Horizon Catalog
   cover natively (discovery, classification, tags, lineage, data quality,
   access history, governance), and which of ours does it not (the glossary
   edges, the exposure manifest, the rule-driven profile pages)? Name each
   duty as covered, partial or missing.
5. **Ontology.** What is Snowflake's business ontology (semantic views and
   related features): does it hold what AutoOntology holds (terms, typed
   relations such as issued by and held by, mappings to columns)? Is it
   generally available, in preview, or announced only, in our region and edition?
6. **AI native.** Which Cortex features (semantic views, Cortex Analyst,
   Cortex Search, agents) read the same gold and the same ontology, and what
   would the agent-facing interface be beside today's agent contract?
7. **Monitoring.** What replaces the Prometheus exporter and Grafana dashboards
   inside Snowflake (event tables, Snowsight dashboards, alerts), and what
   does the load-monitoring skill need to stay the same?
8. **Multi-platform seam.** What must stay the same in the engine so that one
   image and one rules folder run on the local pipeline, AWS and Snowflake?
   Name each place the code assumes one platform.
9. **Cost and latency.** Credits for an always-on pool against load windows,
   against today's local and AWS cost; the latency the hop removal saves
   (database round trips are the load's limit, so measure that first).
10. **Governance.** Roles, network policies and secrets for a service that holds
    provider credentials; how this fits the existing access-audit controls.

## Open questions for the operator

Answered as the research needs them, one at a time, with a recommendation:

- Which edition and region is the account, and are the container service, the
  business ontology and Snowflake Postgres enabled there? (Recommendation: the
  research reads the account's own settings through a read-only role, so this
  is not asked unless that fails.)
- Is "no internet latency" about the load (database round trips) or about
  serving (agents reading gold), or both? (Recommendation: both, load first,
  since the load is database-bound.)
- Is the first target the whole platform at once, or one duty at a time?
  (Recommendation: one duty at a time, catalog and ontology first, because
  they are read-only.)

## Checklist

- [ ] Research items 1 to 10 answered, each with its documentation page and "measured" or "from the documentation"
- [ ] A covered, partial or missing table for the catalog and the ontology duties
- [ ] A recommendation: whole, by duty, or not yet, with the cost and the order
- [ ] Follow-up tickets written for each duty the recommendation keeps (the map's Not yet specified graduates)
- [ ] Learning → skill: name the skill line changed (aws-snowflake-operations or data-catalog), or write "none"

## Answer

(open)

## Comments
