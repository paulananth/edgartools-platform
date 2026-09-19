# Implement Merge Stage and recovery

Type: task
Status: claimed
Owner: Codex
Blocked by: 03

## Work

Implement reviewed bindings, governed roles, deterministic fields, typed relationships, aliases, reversible decisions and fenced publication retries. All unqualified automatic bindings remain disabled.

## Evidence

Shared core implemented with 30 PostgreSQL integration tests passing; 86 existing
API/publication tests also pass. Fresh replay permutations, closure rollback and
three-database command integration now execute. Independent review agents hit a
service usage limit; local review fixed replay, retirement and recovery gaps.
Bounded reversal preview, immutable invocation attempts, temporal-parent tests
and resolution-publication dependencies are now implemented. Full source
disposition accounting and staged large-component reversal remain before this
ticket closes. Runtime source integration is still required by ticket 05.

## Integration checkpoint, 2026-09-19

Native batch accounting and immutable deferred records now commit atomically;
SQL requires blocking reviews in every observing batch and rejects premature
closure. Independent Standards/Spec/GoF reviews of this increment completed,
and their findings were fixed. Reviewed deferred resolution, complete source
publication accounting and staged large-component reversal still block closure.
See [build state](../../../docs/specs/clean-mdm/state-of-build.md).
