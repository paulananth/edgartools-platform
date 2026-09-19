# Decide whether v1/v2 get retired now that the Agent Query Surface exists

Type: grilling
Status: resolved
Blocked by: 01

## Question

Ticket 01 locked zero freshness/provenance identity on Agent Query
Surface results. ADR 0001 defines an Agent-Grade Read — Decision
Watermark present and aligned — as the *only* valid input to a Trading
Decision. Does the v1 Snowflake Decision Contract and v2 Mongo Decision
Projection get retired now that a broader, open-query surface exists,
or do they stay?

## Comments

- 2026-09-19: operator answered "v1/v2 stay."

## Answer

**v1 Snowflake Decision Contract and v2 Mongo Decision Projection
stay.** This is not a scheduling preference between two redundant
surfaces — it is forced by ticket 01: the Agent Query Surface carries no
freshness identity, so it structurally cannot produce an Agent-Grade
Read, and ADR 0001 requires an Agent-Grade Read for any Trading
Decision. Retiring v1/v2 without also dropping that requirement would
leave nothing in the platform able to satisfy it. Neither was proposed
here, so both continue serving their existing consumers, unchanged, per
ADR 0014's own scope boundary. No further ticket needed on this
question unless someone later proposes dropping the Agent-Grade Read
requirement itself — a different, much larger decision than this map's
destination covers.
