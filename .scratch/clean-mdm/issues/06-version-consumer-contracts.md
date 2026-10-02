# Version API export and graph contracts

Type: task
Status: partly built: `ContractReader` and the publication outbox are on main; the hosted consumer cut-over is under Not yet specified in `mastering-to-done/map.md` (2026-10-02 audit, mastering to-do 01).
Was: open
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
