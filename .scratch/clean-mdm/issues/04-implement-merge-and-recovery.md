# Implement Merge Stage and recovery

Type: task
Status: claimed
Owner: Codex
Blocked by: 03

## Work

Implement reviewed bindings, governed roles, deterministic fields, typed relationships, aliases, reversible decisions and fenced publication retries. All unqualified automatic bindings remain disabled.

## Evidence

Shared core implemented with 25 PostgreSQL integration tests passing; 33 existing
publication tests also pass. Fresh replay permutations, closure rollback and
three-database command integration now execute. Independent review agents hit a
service usage limit; local review fixed replay, retirement and recovery gaps.
Reversal preview, full source disposition/attempt accounting and additional
temporal coverage remain before this ticket closes.
