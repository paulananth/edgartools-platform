# 06 — Resolve the MDM_COMPANY export-target circularity

Type: grilling
Status: resolved
Blocked by:

## Question

Ticket 05's implementation plan (enrich `COMPANY` by left-joining `MDM_COMPANY`,
then later replace `MDM_COMPANY` with a compat view over the enriched
`COMPANY`) was never designed to notice that `MDM_COMPANY` is the **only**
Snowflake-side landing target `edgar_warehouse/mdm/export.py`'s
`DOMAIN_TO_TABLE` MERGEs into from MDM Postgres — there is no separate
raw/staging table. Once the compat-view swap happens, `company.sql`'s join
would read from a view defined as a projection of `COMPANY` itself:
self-referential, won't compile. Tickets 01–04 did not surface or resolve
this because the design work happened at the "what should the final shape
be" level, not the "what does the physical write path look like mid-cutover"
level.

What is the correct non-circular physical sequencing: does the MDM export's
write target get renamed to a new raw/staging table name (e.g.
`STG_MDM_COMPANY`) that `company.sql` joins against, leaving the
public-facing `MDM_COMPANY` name free to become the compat view — or is
there a different resolution?

## Answer

**Rename now, not at cutover.** `edgar_warehouse/mdm/export.py`'s `DOMAIN_TO_TABLE["company"]`
target renames from `MDM_COMPANY` to **`MDM_COMPANY_ENTITY`** immediately (not deferred
to the eventual cutover moment) — `company.sql` joins `MDM_COMPANY_ENTITY` from day
one, and the public `MDM_COMPANY` name is free to become the compat view as soon as
the enriched `COMPANY` lands, with no later two-step rename-and-swap required.

**Considered and rejected: moving the export target into `EDGARTOOLS_SOURCE`.**
Checked live: `EDGARTOOLS_SOURCE` has zero MDM tables today, and `edgar_warehouse/mdm/*.py`
never references that schema. This isn't an oversight — per CONTEXT.md/CLAUDE.md,
`EDGARTOOLS_SOURCE` is specifically "external stage + tables auto-refreshed from S3
via Snowflake native S3 pull," one write mechanism, one pipeline. MDM's export is a
categorically different mechanism (Python/SQLAlchemy MERGE from MDM's own Postgres,
no S3/native-pull involved) — landing it in Source would mix two unrelated write
paths into a schema whose entire contract is "there is exactly one way data lands
here." The table stays in `EDGARTOOLS_GOLD`, alongside the other 4 MDM export
targets (`MDM_ADVISER`, `MDM_PERSON`, `MDM_SECURITY`, `MDM_FUND`) — this was never
a layering problem, just a same-schema self-reference problem.

**Naming: `MDM_COMPANY_ENTITY`, not `MDM_COMPANY_RAW`/`STG_MDM_COMPANY`.** "RAW"
was rejected because it implies bronze/source-layer semantics this table doesn't
have — it's a gold-schema MDM entity table like its 4 siblings, just renamed to
free up the compat-view name. `_ENTITY` matches how the other 4 export targets
already read ("the entity record for this domain").

**Net effect on ticket 05's scope:** adds one line to ticket 05 — rename the
`"company"` entry in `DOMAIN_TO_TABLE` from `MDM_COMPANY` → `MDM_COMPANY_ENTITY`,
plus the corresponding DDL rename in `infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql`
— before `company.sql`'s enrichment join is written. Everything else in ticket 05's
original scope (enrich `COMPANY`, compat view, migrate readers, stop dual export)
proceeds unchanged; the join target is simply `MDM_COMPANY_ENTITY` instead of the
now-freed `MDM_COMPANY` name.
