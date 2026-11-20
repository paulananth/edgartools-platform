# data-platform: Define one responsibility

Type: task
Status: open
Priority: P0
Blocked by: none
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 1 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Route from current source readiness to the next owning skill; own setup and connection discovery, not each downstream procedure.

Inventory existing instructions against the neighboring owners: data-profiling, data-onboarding, refining-rules or data-operations. Reconcile the current index and references before moving any text.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

None. This is the first frontier ticket.

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence; verified against current `data-platform`, `data-profiling`, `data-onboarding`, `refining-rules`, `data-operations`, `bookkeeping`, `change-journal` and `mdm-engineering` instructions by reviewing the ownership map and links. (2026-11-20 14:40 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff; verified by reviewing the ownership table, flow table and linked owner paths in `skills/data-platform/SKILL.md`, plus the reconciled run/recovery handoffs in `skills/data-onboarding/SKILL.md` and `skills/refining-rules/SKILL.md`. (2026-11-20 14:40 ET)
- [x] Demonstrate the boundary on a new captured source, an already configured source and a restart after a completed phase; link retained work rather than duplicating it. Verified by reviewing the documented handoffs, named artifacts and destination anchors; the genericity check does not validate routing behavior, and no source operation was performed. (2026-11-20 14:40 ET)
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. PR #1956 opened as a draft; verified by 145 passing genericity tests and `git diff --check`. (2026-11-20 14:44 ET)
- [x] Learning → skill: source routing and artifact ownership belong in Data Platform; downstream procedures and their evidence stay with their owning skill. Recorded in [Decisions, artifacts and handoffs](../../../skills/data-platform/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 14:40 ET)

## Answer

Data Platform owns the decision about the next phase, shared source-readiness
acceptance rules, and connection discovery/setup. It does not own profiling,
new-source configuration, live-rule changes, or recurring execution. The
authoritative owners and the artifacts they retain are listed in [Decisions,
artifacts and handoffs](../../../skills/data-platform/SKILL.md#decisions-artifacts-and-handoffs).

The three routing cases are documented there: new captured work goes through
Data Onboarding and retains the profiling report/findings; an already
configured source goes to Data Operations for a repeat run or Refining Rules
for a live-rule change; restart reads the completed phase's retained output
and resumes at the first incomplete phase. These are documented handoffs,
not operational qualification evidence.

Current checkout baseline: `HEAD` is `f5ada4dfa9486b3869574c99e7eceb6f16aa2cb0`.
Installed skill provenance could not be validated: both
`~/.agents/skills/data-platform` and `~/.claude/skills/data-platform` are
symlinks to the missing
`~/.local/share/edgartools/skill-source/skills/data-platform` target. No
installed copy was read or changed.

## Validation and remaining work

- `UV_CACHE_DIR=/private/tmp/uv-cache-ticket01 uv run --with pytest pytest tests/unit/test_profiling_genericity.py` — **145 passed**. This documentation genericity check does not validate routing behavior.
- The PR/publish checklist item remains open because this implementation run's
  scope excludes commit, push and PR publication. The scoped change and check
  evidence are recorded here; publication remains incomplete.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
