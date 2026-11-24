# data-quality: Make the entrypoint executable

Type: task
Status: resolved
Priority: P0
Blocked by: 03, 09, 15, 26
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-quality](../../../skills/data-quality/SKILL.md)
Step: 3 of 6
Skill dependencies: data-profiling, data-modeling
Applicability: Every source with field constraints, defects or downstream quality obligations.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: profiling quality findings, mapped fields and the existing quality grammar. Outputs: quality.yaml or table checks, measured failure counts and explicit row dispositions. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/data-quality/SKILL.md: plan, measure, decide, write, Publish quality meaning to the business catalog. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [data-profiling: Make the entrypoint executable](./09-data-profiling-entrypoint.md); [data-modeling: Make the entrypoint executable](./15-data-modeling-entrypoint.md); [data-quality: Reconcile shared rules](./26-data-quality-consistent-rules.md)

Priority rationale: Measured checks and dispositions prevent unsafe mappings.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Produce a concise entrypoint that consumes approved profiling findings and mapped fields and routes MDM checks versus silver table checks; verified in [Start here](../../../skills/data-quality/SKILL.md#start-here-route-a-quality-phase) (2026-11-24 07:52 ET).
- [x] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail. `draft --help` and `measure --help` show the documented arguments; the guide-path and skill-size checks pass (2026-11-24 07:52 ET).
- [x] Walk an invented code-list finding through `in_set@1`, measurement and the Data Onboarding handoff; documented in the answer. No source data or load was used (2026-11-24 07:52 ET).
- [x] Publish the scoped change and evidence in its own branch and PR; local affected checks **158 passed**. [docs(data-quality): make the entrypoint executable](https://github.com/paulananth/edgartools-platform/pull/2096) (2026-11-24 07:56 ET).
- [x] Learning → skill: the entrypoint routes new versus live feed quality phases to their existing owner; recorded in Data Quality's [Start here](../../../skills/data-quality/SKILL.md#start-here-route-a-quality-phase) (2026-11-24 07:52 ET).

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Answer

Data Quality now starts with a short route for new-feed MDM quality work, live-feed measurement, silver-spec checks, and read-only mastered-entity audits. The exact supported `draft` and `measure` command forms are in the entrypoint; detailed check, disposition, row-marking and publication rules remain in their existing sections. Hard stops remain required.

Static walkthrough (invented): an approved new-feed `code_list` finding maps to a record field; `draft` proposes `in_set@1`, `quality.yaml`, `expected.yaml` and `QUALITY.md`; `measure` checks JSON Lines records and verifies a planted failing value. Data Quality applies the `decide` table and records any hierarchy row disposition; the resulting artifacts go to Data Onboarding. This is a document trace, not a source run or new test scenario.

The [Data Quality skill](../../../skills/data-quality/SKILL.md#start-here-route-a-quality-phase) distinguishes MDM quality from silver checks, new-feed Data Onboarding from live-feed Refining Rules, and optional audits/catalog publication from the main path. Its installed copy differs; it was read for provenance and left unchanged.

## Validation

- `quality_plan.py --help`, `draft --help` and `measure --help` confirmed the referenced command names and options.
- `tests/unit/test_profiling_genericity.py`, `tests/unit/test_guides_name_existing_paths.py`, and the Data Quality skill-size check: **158 passed**.
- `git diff --check`: clean.
