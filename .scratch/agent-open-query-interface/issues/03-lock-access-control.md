# Lock access control for the Agent Query Surface

Type: grilling
Status: resolved
Blocked by: 02

## Question

Ticket 02 locked the shape: an MCP server, raw SQL, two backends
(Snowflake, Postgres). An agent can write **any** `SELECT` — arbitrarily
expensive, arbitrarily broad, no pre-approved question list to bound it.
That's a materially bigger blast radius than anything else this platform
exposes to an agent today. Three mostly-independent things need locking:

1. **Authentication to the MCP server**: one shared service credential
   the MCP server presents to callers (the same pattern as the existing
   `require_api_key` / `X-API-Key` model in `edgar_warehouse/mdm/api/`),
   or per-agent/per-caller credentials issued individually?
2. **Authorization enforcement at the backend**: a dedicated read-only
   DB role with `SELECT`-only grants enforced by Snowflake/Postgres
   themselves (the same shape as the existing `EDGARTOOLS_PROD_READER`
   role, which already holds `SELECT`-only on gold) — or does the MCP
   server enforce read-only purely in its own code (parsing/rejecting
   non-`SELECT` statements before they reach the database)?
3. **Resource governance / blast radius**: does an unconstrained agent
   query need guardrails — a statement timeout, a row/byte cap, a
   dedicated low-priority Snowflake warehouse separate from the
   production refresh warehouses — to stop one expensive or malformed
   query from degrading a shared production system this platform
   depends on? Or is this deferred to implementation, not decided here?

## Comments

- 2026-09-19 all three accepted as recommended, one pass: shared service
  credential (Q1), DB-level read-only role (Q2), resource-governance
  principle locked with exact numbers deferred (Q3).

## Answer

1. **Authentication**: one shared service credential the MCP server
   presents/validates for callers, the same `X-API-Key` /
   `require_api_key` pattern already used by `edgar_warehouse/mdm/api/`.
   Not per-agent/per-caller credentials. Consistent with ADR 0001's
   Deferred Access Control (v2 Mongo already uses one shared read-only
   SCRAM user for all internet agents, not per-agent). A pluggable
   per-caller access layer stays available later behind this same door;
   not built now.
2. **Authorization**: a dedicated read-only DB role with `SELECT`-only
   grants, enforced by Snowflake and Postgres themselves — the same
   shape as the existing `EDGARTOOLS_PROD_READER` role
   (`SELECT`-only on gold). This is the real boundary. Server-side
   rejection of non-`SELECT` statements in the MCP tool is a fast-fail
   layered on top, not a substitute for the DB-level grant.
3. **Resource governance**: locked as a principle, not a number. An
   agent-authored query must not be able to degrade production refresh
   (gold dynamic tables, silver loads) or MDM's operational workload.
   Mechanism: a separate Snowflake warehouse / Postgres connection pool
   dedicated to this surface, with a statement timeout — not sharing the
   production refresh warehouse or MDM's operational connection pool.
   Exact timeout/row-cap values are implementation detail, deferred.
