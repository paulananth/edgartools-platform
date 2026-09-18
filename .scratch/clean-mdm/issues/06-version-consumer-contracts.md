# Version API export and graph contracts

Type: task
Status: open
Owner: Codex
Blocked by: 05

## Work

Expose shared identities, roles, provenance, aliases and reported/derived relationships. Verify consumer migration and publication completeness and recovery offline.

## Evidence

An opt-in authenticated v2 read API now exposes shared identities, profile-field
provenance, aliases and generation-pinned pages. PostgreSQL-backed API tests and
legacy API regression tests execute. This is an independently testable read
contract; native source integration, hosted export/graph materialization,
consumer crosswalks and activation remain incomplete.
