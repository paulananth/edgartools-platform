# Database choice and database-agnostic merge requirements

Status: in progress — fixing PR #1070's generic-skill CI failure; not merged.

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
- [x] Review Standards, Spec and GoF, then create a separate skill PR without merging it; [PR #1070](https://github.com/paulananth/edgartools-platform/pull/1070) is open, CI pending — 2026-10-17 20:27 ET.
- [x] Reproduce the CI failure and identify its cause; the existing genericity test fails locally with four named-domain occurrences outside Examples — 2026-10-17 20:34 ET.
- [x] Keep per-engine qualification generic and move named fixture cohorts into Examples; existing genericity test unchanged and now passes — 2026-10-17 20:35 ET.
- [x] Run the affected genericity tests, skill validation and doctor; 70 passed with 2 previously passing cases deselected by testmon, four skill validators passed, doctor resolved all 146 examples, and the three-axis review below passed — 2026-10-17 20:35 ET.
- [ ] Push the correction and verify all checks on the final PR head, with a bounded CI monitor that exits on success, failure, PR closure or deadline.
- [x] Learning → skill: MDM engineering now keeps qualification instructions generic for every affected kind/source and places concrete domain fixture cohorts under Examples; engine choice and shared merge requirements remain intact — 2026-10-17 20:35 ET.

## CI diagnosis

CI run `39082834619`, Unit tests: the genericity guard rejected Company and
Person in the new qualification section and proof table. The local targeted
test reproduced the same four occurrences in 0.14 seconds. This deterministic
documentation-lint failure needs no competing runtime hypotheses or temporary
instrumentation; the existing regression test is the correct feedback loop.
The previous skill/command validators do not enforce generic-domain wording.

CI-fix review: **Standards** — the existing genericity guard stays unchanged;
only the skill wording and this ticket change. **Spec** — all three engines
retain the same shared merge contract, with concrete domain fixtures retained
as examples. **GoF** — the reviewer skill is available; no application code or
module structure changes, so no design-pattern refactor is warranted.

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
