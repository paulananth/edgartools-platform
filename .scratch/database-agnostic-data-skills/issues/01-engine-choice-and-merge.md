# Database choice and database-agnostic merge requirements

Status: in progress

Operator ruling: fix the skills to allow the selected database and make the
merge logic database agnostic in the MDM engineering skill. This is a skill
contract change; runtime implementation and database initialization remain
separate work and must not be claimed from documentation edits.

## Checklist

- [x] Inspect live main, worktrees, current skill guidance and runtime refusals; fresh branch at `c62bce95`, planned-path and actual overlap guards passed — 2026-10-17 20:26 ET.
- [x] Make database selection explicit in data-platform and data-operations; reviewed that a dialect refusal routes engineering work and never silently substitutes PostgreSQL — 2026-10-17 20:26 ET.
- [x] Make MDM engineering own database-agnostic merge computation, storage boundaries and per-engine behavioral qualification; reviewed the shared algorithm, destination guarantees and Company/Person parity requirements — 2026-10-17 20:26 ET.
- [x] Align SQL-writer with the shared merge contract and complete store migration/registration requirements; reviewed that portable table DDL alone cannot count as initialized or registered — 2026-10-17 20:26 ET.
- [x] Validate changed skills, internal references and command examples; four skill validators passed, doctor returned `ok: true`, all 146 command examples and links resolved in both the checkout and an isolated skills-only copy; no application tests required for these Markdown-only changes — 2026-10-17 20:26 ET.
- [ ] Review Standards, Spec and GoF, then create a separate skill PR without merging it.
- [ ] Learning → skill: name the changed instructions and their lesson.

## Standards

Only four skill files and this checklist change on a dedicated Codex branch.
Existing user narration and approval rules are preserved. No installed skill,
runtime code, database or active workstream is changed. Validation uses current
checkout modules with an existing dependency environment, without rebuilding
or mutating that environment. Whitespace and overlap checks passed.

## Spec

PostgreSQL, MySQL and SQL Server remain operator-selectable targets. The skills
now distinguish that contract from the five PostgreSQL-only implementations.
MDM engineering owns one shared configured Rust/Python merge algorithm and
database-specific storage adapters, with authoritative transaction, freshness,
uniqueness, lease/fence, authorization and recovery enforcement retained.
The same Company and Person behavior must be qualified on all three engines,
including any other affected kinds/sources. No runtime portability is claimed.

## GoF

The GoF reviewer is available and was read in this session. This diff changes
instructions only. The storage boundary describes responsibilities without
mandating a class hierarchy or performing an unqualified runtime refactor.
The current code and its history remain the evidence required before a future
implementation chooses a concrete interface or pattern.
