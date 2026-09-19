# MDM Postgres DDL inventory (current state, for the Agent Query Catalog)

Ticket: `.scratch/agent-open-query-interface/issues/05-inventory-mdm-postgres-ddl.md`
Checked live: 2026-09-19, against the local Postgres 16 instance documented
in `.scratch/clean-mdm/local-postgres.md` (container
`edgartools-clean-mdm-pg16`, read-only introspection only — no writes, no
Clean MDM file/branch/worktree touched).

**This is a current-state inventory, expected to move.** Clean MDM is
actively rebuilding this schema (shared Company/Person identities,
governed profiles, a Merge Stage — none landed as of this check). Treat
this as raw input to the Agent Query Catalog, not a settled catalog.

## Database layout: four separate local databases, one of them is "MDM"

| Database | Tables | What it is |
| --- | --- | --- |
| `mdm` | 27 | The MDM domain schema itself — entities, relationships, governance config |
| `change_ledger` | 11 | Acquisition/source tracking (`source_*` tables) |
| `bookkeeping` | 10 | Warehouse-side operational tracking (SEC sync state, pipeline runs) — **not MDM data** |
| `silver` | 6 | SEC silver landing rows loaded locally for mastering tests — **not MDM data** |

27 (`mdm`) + 11 (`change_ledger`) = 38, matching Clean MDM ticket 03's
figure ("38 tables, migrations 001–022") exactly. `bookkeeping` and
`silver` are separate concerns, not part of that count — flagged so a
future reader doesn't conflate "38 tables" with "everything in this
Postgres cluster."

**Open scoping question this research surfaces but does not resolve**:
does "MDM (Postgres)" in the Agent Query Surface destination mean the
`mdm` database only (27 tables), or does it also cover `change_ledger`
and/or `bookkeeping`? Those two are warehouse/acquisition internals, not
domain entity data — my read is they're out of scope for an agent asking
business questions, but this wasn't asked and isn't decided here.

**One fact worth surfacing for the Agent Query Catalog design**: the
graph relationship data (`mdm_relationship_instance`,
`mdm_relationship_type`) lives inside the same `mdm` database as the
entity tables — not a separate "graph" connection. For the Postgres
backend, "MDM" and "graph (Postgres mirror)" named separately in this
map's Destination are the same database, same DSN. (Whether this holds
for the eventual Snowflake-hosted target, once that's back in scope, is
a separate question — deferred with the rest of the Snowflake side.)

## `mdm` database: 27 tables by category

**Core entity identity** — one `mdm_entity` parent row per resolved
entity, plus one typed child table per entity kind:

- `mdm_entity` (10 cols) — `entity_id` (UUID, PK), `entity_type`,
  `is_quarantined`, `resolution_method`, `confidence`, `valid_from`/
  `valid_to`, `version`. The shared identity spine every typed table FKs
  into.
- `mdm_company` (15 cols) — `cik`, `canonical_name`, `ein`, `sic_code`,
  `state_of_incorporation`, `ticker`/`primary_ticker`/`primary_exchange`,
  `tracking_status`, `parent_company_entity_id` (self-referential FK via
  `mdm_entity`). 3 rows (Apple, Microsoft, Amazon — the local smoke test).
- `mdm_person` (9 cols) — `owner_cik`, `canonical_name`, `name_variants`
  (JSONB), `primary_role`, `role_titles` (JSONB),
  `affiliated_company_count`. 0 rows.
- `mdm_adviser` (13 cols) — `cik`, `crd_number`, `sec_file_number`,
  `adviser_type`, `hq_city`/`hq_state`, `aum_total`, `fund_count`,
  `linked_company_entity_id`. 0 rows.
- `mdm_fund` (10 cols) — `adviser_entity_id`, `private_fund_id`,
  `fund_type`, `jurisdiction`, `aum_amount`, `aum_as_of_date`. 0 rows.
- `mdm_security` (9 cols) — `issuer_entity_id`, `canonical_title`,
  `security_type`, `cusip`, `isin`, `security_class`. 0 rows.
- `mdm_audit_firm` (6 cols) — `firm_name`, `pcaob_firm_id`, `big4`. 10
  rows (seeded).

**Source binding**:

- `mdm_source_ref` (7 cols, composite PK `entity_id, source_system,
  source_id`) — `source_priority`, `confidence`, `matched_at`,
  `source_content_hash`. 3 rows.

**Relationship model** — this is the graph, stored relationally:

- `mdm_relationship_type` (11 cols) — `rel_type_name`,
  `source_node_type`/`target_node_type` (FK to
  `mdm_entity_type_definition`), `direction`, `is_temporal`,
  `dedup_key_fields` (JSONB), `merge_strategy`. 11 rows (config, e.g.
  `IS_INSIDER`, `EMPLOYED_BY`, `MANAGES_FUND` per the CLAUDE.md glossary
  of relationship types).
- `mdm_relationship_instance` (23 cols, the widest table) —
  `source_entity_id`/`target_entity_id` (both FK `mdm_entity`),
  `rel_type_id` (FK), `properties` (JSONB), `effective_from`/
  `effective_to`, `valid_from_date`/`valid_to_date`, `date_provenance`,
  `relationship_kind`, `source_evidence` (JSONB),
  `superseded_by_version_id` (self-FK — versioning chain),
  `quarantined`/`quarantine_reason`, `graph_synced_at`, `run_id`. 0 rows.
- `mdm_relationship_property_def` (7 cols) — typed property schema per
  relationship type. 46 rows.
- `mdm_relationship_coverage` (10 cols), `mdm_relationship_source_mapping`
  (14 cols, 11 rows), `mdm_relationship_source_priority` (7 cols),
  `mdm_relationship_derivation_checkpoint` (7 cols) — derivation
  bookkeeping for the relationship pipeline, not agent-facing data per
  se; flagged for the catalog design to classify as internal vs. queryable.

**Governance / config** (mostly populated, drives resolution behavior,
not itself "the data"):

- `mdm_entity_type_definition` (7 cols, 6 rows), `mdm_field_survivorship`
  (10 cols, 11 rows), `mdm_normalization_rule` (8 cols, 47 rows),
  `mdm_match_threshold` (8 cols, 5 rows), `mdm_source_priority` (8 cols,
  4 rows).

**Operational / staging** (pipeline internals):

- `mdm_entity_attribute_stage` (10 cols, 33 rows), `mdm_match_review` (9
  cols, 0 rows), `mdm_pipeline_lease` (7 cols, 0 rows),
  `mdm_publication_request` (15 cols, 0 rows), `mdm_change_log` (7 cols,
  3 rows).

**Graph generation bookkeeping** (Snowflake-side graph publish concepts,
mirrored here — currently empty locally since graph publish/reconcile
still needs Snowflake, per `local-postgres.md`):

- `mdm_graph_generation` (9 cols, 0 rows), `mdm_graph_partition` (19
  cols, 0 rows).

## Current population state (why most of this is empty)

Only `mdm_company` (3), `mdm_audit_firm` (10 seeded),
`mdm_source_ref` (3), `mdm_change_log` (3), and the governance/config
tables have any rows. `mdm_person`, `mdm_adviser`, `mdm_fund`,
`mdm_security`, and `mdm_relationship_instance` are all 0 rows locally —
consistent with `local-postgres.md`'s own note that the bounded local
load only captured company-level data (`--artifact-policy skip` never
fetched ownership XML, ADV, or 13F holdings), so person/security/fund/
adviser mastering and relationship derivation have no source data to run
against yet in this environment.

## What this means for the Agent Query Catalog (not decided here)

- A catalog entry per table needs: table purpose, column meanings/null
  semantics (most are undocumented at the DB level — comments would need
  to come from code or be authored fresh), and the FK graph above as the
  "relationships" half of the catalog.
- `mdm_entity` + its typed children is a classic single-table-inheritance
  shape — the catalog should probably describe this pattern explicitly
  (join `mdm_entity` to the right typed table by `entity_type`) rather
  than listing 7 unrelated tables.
- `mdm_relationship_instance` already carries versioning
  (`superseded_by_version_id`) and temporal validity
  (`valid_from_date`/`valid_to_date`) — an agent querying "current"
  relationships needs to know to filter on these, the same currency
  rules `CONTEXT.md`'s **Current Neighborhood** term already documents
  for the bundle-based surfaces. Whether the Agent Query Catalog
  restates this rule or leaves the agent to discover it from the schema
  alone is a catalog-design question, not resolved by this inventory.
- Whether operational/staging/governance tables (leases, staging,
  normalization rules) belong in the agent-facing catalog at all, or
  should be excluded as internal-only, is also not decided here — this
  research only inventories what exists.
