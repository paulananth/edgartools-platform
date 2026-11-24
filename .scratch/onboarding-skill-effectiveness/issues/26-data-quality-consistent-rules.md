# data-quality: Reconcile shared rules

Type: task
Status: claimed
Priority: P0
Blocked by: 02, 08, 14, 25
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-quality](../../../skills/data-quality/SKILL.md)
Step: 2 of 6
Skill dependencies: data-profiling, data-modeling
Applicability: Every source with field constraints, defects or downstream quality obligations.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: quality.yaml or table checks, measured failure counts and explicit row dispositions.

Start from skills/data-quality/SKILL.md: plan, measure, decide, write, Publish quality meaning to the business catalog. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [data-profiling: Reconcile shared rules](./08-data-profiling-consistent-rules.md); [data-modeling: Reconcile shared rules](./14-data-modeling-consistent-rules.md); [data-quality: Define one responsibility](./25-data-quality-responsibility.md)

Priority rationale: Measured checks and dispositions prevent unsafe mappings.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition. Verified by reconciling `CLAUDE.md`, Data Platform, Data Onboarding, Data Profiling, Data Modeling, Refining Rules, Business Catalog and Bookkeeping recovery; recorded under [Inventory and disposition](#inventory-and-disposition). (2026-11-20 20:01 ET)
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries. Verified in the Data Quality skill's [Shared rules and gates](../../../skills/data-quality/SKILL.md#shared-rules-and-gates) and its [decisions and handoffs](../../../skills/data-quality/SKILL.md#decisions-artifacts-and-handoffs): `quality.yaml` or silver table checks, measured counts, and explicit hierarchy-row dispositions remain distinct artifacts. (2026-11-20 20:01 ET)
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred. Verified by static trace through the Data Quality modes and their owner handoffs; recorded under [Routine and blocked paths](#routine-and-blocked-paths). No workflow or source execution was run. (2026-11-20 20:01 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. The operator lifted the prior no-PR restriction in this session.
- [x] Learning → skill: Shared approval, access and completion rules stay at their authoritative repository or phase owner; Data Quality links to them and owns only check meaning, measured counts and row dispositions. Recorded in [Shared rules and gates](../../../skills/data-quality/SKILL.md#shared-rules-and-gates). (2026-11-20 20:01 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Inventory and disposition

| Concern | Existing overlap or conflict | Authority and disposition |
|---|---|---|
| Approval and activation | The `decide` section applies the standing rule to measured dispositions; that wording could be mistaken for approval to change or activate a source. | [CLAUDE.md, Talking with the operator](../../../CLAUDE.md#talking-with-the-operator) and Data Onboarding's [hard stops](../../../skills/data-onboarding/SKILL.md#hard-stops) govern. Clarify that a disposition is not approval for a source change, new kind, load or switch-on; preserve the owner's approval gate. |
| Provider access and secrets | Data Quality's source-local evidence workflow overlaps with repo-wide access and secret handling. | [CLAUDE.md, Commits, PRs and secrets](../../../CLAUDE.md#commits-prs-and-secrets) and Data Platform's [hard stops](../../../skills/data-platform/SKILL.md#hard-stops) govern. Work from retained local evidence, request permission before provider access, and keep secrets out of output. |
| Configuration-only work and local proof | Planning and measurement could be read as permission to write configuration or run a load. | Data Onboarding owns new-feed configuration; Refining Rules owns live-feed changes. Their check/load gates govern. Data Quality measures and recommends; the plan does not execute a source load. |
| Test scenarios | The measurement helper requires a planted record for each check, which could be mistaken for approval to add scenario/test code. | [CLAUDE.md, How to work in this repo](../../../CLAUDE.md#how-to-work-in-this-repo) and the owner phase's check/load gate govern. The existing planted-record check validates the configured helper; it grants no authority for new test scenarios or a load. No scenario/test code was added. |
| Completion wording | A successful measurement or configuration validation could be overstated as execution or publication. | [CLAUDE.md, Task checklists](../../../CLAUDE.md#task-checklists) and [Talking with the operator](../../../CLAUDE.md#talking-with-the-operator) govern. Report only verified evidence; execution results and catalog publication require their own evidence. |

The repository `skills/README.md` already routes each task to its owner, so no
index edit was needed. The current skill's ownership table already applies the
shared input/output disposition: profiling findings are inputs; MDM checks and
fixes use `quality.yaml`; silver checks live in the table's checks; `QUALITY.md`
records measured counts and decisions; each invalid hierarchy row stays marked
with an evidence-backed fix or `needs_steward` disposition. No output format or
owner was duplicated.

## Routine and blocked paths

**Routine path (static trace):** an approved profiling finding and accepted
model decision feed Data Quality. It plans supported checks, measures counts on
the records the checks read, records the decision and disposition, then hands
new-feed configuration to Data Onboarding or a live-feed change to Refining
Rules. Data Catalog owns the business definitions; Bookkeeping owns receipt
admission. The skill adds no authority beyond these handoffs.

**Blocked path (static trace):** missing approval or required measurements goes
back to the owning phase; an unsupported check is implementation work; a
hierarchy row without evidence stays marked for steward decision; a needed
provider request requires permission; missing credentials are set by the
operator in their terminal. No guessed approval, provider access, load or
switch-on is inferred. These are document traces, not behavioral execution.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py` — **155 passed** in the closeout worktree. This checks source-neutral wording; it does not validate workflow behavior.
- `git diff --check` — clean.
- `gstack-skill-bill` on the edited skill — **28,088 bytes** (26,102 bytes at `HEAD` before the edit); the installed skill is a different copy and was not used as the edit source.

The skill's installed link resolves to a separate checkout at `3884e81`; its
`SKILL.md` hash differs from this worktree's file. `origin/main` and this
worktree were both at `d650395c6` before edits. The prerequisite commits are in
the current history: tickets 25/#1984 (`d650395c6`), 37/#1981 (`51859666f`),
and 61/#1982 (`fcd075b6c`). The separate installed checkout has unrelated
dirty changes; it was left untouched. No other ticket files were edited.

## Answer

The repository Data Quality skill already points shared approval, provider-access, secret, testing and completion rules to `CLAUDE.md` or the owning phase. Its local contract remains check/fix meaning, measured counts, and evidence-backed invalid-row dispositions. The audit found no duplicate policy or owner requiring another skill edit.

The installed Data Quality copy differs from the repository copy and was read for provenance only; it was not edited. This ticket reconciles the repository skill, not the installed tree.

The relevant skill guidance was published in [Ticket 26: point data-quality rules at their homes](https://github.com/paulananth/edgartools-platform/pull/1989). The operator lifted the prior no-PR restriction on 2026-11-24. This closeout publishes the resolution and map index; it changes no source rules, loads no data, and adds no test scenarios.
