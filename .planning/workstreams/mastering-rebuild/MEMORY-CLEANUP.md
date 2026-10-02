# Authorized memory cleanup, prepared but not applied

> **Superseded in part by Claude's continuation (2026-10-02 ET),
> `.planning/workstreams/mastering-qualification-claude/TICKET.md`:**
> - The acceptance's synthetic EMPLOYED_BY link is replaced. It now uses a GLEIF accounting parent between two Companies, read by the real GLEIF reader. The test passes on PostgreSQL 16.
> - The CLAUDE.md/AGENTS.md consolidation is reverted. It is now its own ticket (`.scratch/agent-guides/issues/01-consolidate-claude-and-agents-md.md`; operator, 2026-10-02: "Split it out (Recommended)").
> - The local database inventory is done; see that ticket.
>
> Lines below that say otherwise are history.

Operator requested memory cleanup on 2026-10-01 as part of the fresh mastering
branch. External Codex and Claude memory folders are outside this session's
writable roots. This file is the reviewable update; it is not evidence those
external memories were changed.

## Codex update note

Submit one dated note under `~/.codex/memories/extensions/ad_hoc/notes/`.
Do not rewrite the generated MEMORY.md or delete historical rollout evidence.

Supersede implementation guidance that identifies legacy MDM tables or
`mdm_v2` as the active schema. Current mastering lives in
`edgar_warehouse/mdm/clean/`, schema `mdm`, from the rebased platform-validation
baseline. The executable CLI offers Rules, Bookkeeping, Change Journal,
Clean MDM and Snowflake environment resolution. Retired warehouse and legacy
MDM commands must be verified against `--help`, not restored from memory.

Company and Person have separate source contracts and merge-kind files over
the common engine. Person feed 1 is individual-filer submissions. GLEIF links
name explicit child/parent subjects, retain one identity across periods, and
require accepted canonical endpoints. Additional Person role/entity feeds
remain separate onboarding work; the local synthetic employment acceptance
fixture establishes no real-world relationship.

AGENTS.md is the shared instruction source; CLAUDE.md points there. Deployment
state, database usage, timings and completion claims must be refreshed live.
For this task the operator selected local qualification only. Docker is
unavailable in the restricted session: no PostgreSQL qualification, database
deletion, hosted deployment or external memory modification was completed.

Preserve operator decisions, shared-worktree protection, exact governance
approvals, fixture hashes and dated historical evidence.

## Claude update

`project_v2_clean_mdm_is_the_priority.md` says schema `mdm_v2` and the single
`rules` skill are current. Update only those implementation references to
schema `mdm` and the split Data Onboarding / Refining Rules skills. Keep the
operator's rebuild decision, captured-bronze measurement rule and governance
approval requirement.

Keep `project_relationships_with_mdm.md`: it records the operator's requirement
to master person/role/entity links together. Do not erase this as unused.
Keep standing feedback, especially branch/worktree protection, checklists,
local ET timestamps, source trace beside records, exact approvals and bounded
tests. Session-specific no-code instructions remain attached to their original
session; this task explicitly authorized implementation and deletion.
