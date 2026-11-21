# data-governance: Define one responsibility

Type: task
Status: open
Priority: P1
Blocked by: 01, 13
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-governance](../../../skills/data-governance/SKILL.md)
Step: 1 of 6
Skill dependencies: data-modeling
Applicability: Every source's governed outputs and lineage claims.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Define which source-to-output evidence and lineage a steward may trust, independently of catalog-specific mechanics.

Inventory existing instructions against the neighboring owners: data-catalog for business presentation and a destination-specific skill for publication. Reconcile the current index and references before moving any text.

Start from skills/data-governance/SKILL.md: What is governed, Completion; LINEAGE.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md)

Priority rationale: Governed output and lineage meaning precede catalog presentation.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence; verified against `skills/data-governance/LINEAGE.md`, `sources/sec.company/source.yaml`, and the named owner skills in the responsibility table. (2026-11-20 19:39 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff; verified by checking the handoff table and its linked Data Modeling, Data Catalog, Data Operations and OpenMetadata sections against their current skill text. (2026-11-20 19:39 ET)
- [x] Demonstrate the boundary on a governed input, a transient intermediate, a failed processing step and a trusted output; link retained work rather than duplicating it. Documented walkthrough below links the existing Company lineage example and source configuration; the failed-step case states the evidence boundary and does not claim an actual failed run. (2026-11-20 19:39 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. `UV_CACHE_DIR=/private/tmp/uv-cache-ticket61 uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py` passed (142 tests), and `git diff --check` passed. Publication remains open because this task explicitly prohibits commits and PR creation. The genericity check validates wording constraints, not lineage behavior.
- [x] Learning → skill: governance owns the evidence-backed source-to-output lineage contract, while business meaning, catalog projection, destination publication and runtime recovery hand off to their named skills; recorded in [Decisions, evidence and handoffs](../../../skills/data-governance/SKILL.md#decisions-evidence-and-handoffs). (2026-11-20 19:39 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Answer

Data Governance decides which configured source evidence, controls, failable
steps and their checks belong on a steward's trusted path, and which outputs
are supported by that evidence. Its inputs are source contracts and reads,
step order and declared checks, control-file dependencies, and available run
evidence. Its output is the neutral lineage contract in
[LINEAGE.md](../../../skills/data-governance/LINEAGE.md), with configured
intent kept distinct from observed completion. The ownership and handoff table
is in [Decisions, evidence and handoffs](../../../skills/data-governance/SKILL.md#decisions-evidence-and-handoffs).

The boundary walkthrough reuses the existing [Company example in LINEAGE.md](../../../skills/data-governance/LINEAGE.md#examples)
and its [source configuration](../../../sources/sec.company/source.yaml):

| Case | Governance decision | Retained evidence |
|---|---|---|
| Governed input | A captured feed and a named reference read by the target enter as sources. The example names SEC submissions and the ticker reference. | [LINEAGE.md, Examples](../../../skills/data-governance/LINEAGE.md#examples); source `bookkeeping.targets.mastering` and `dataset_contracts` in [source.yaml](../../../sources/sec.company/source.yaml). |
| Transient intermediate | A target-written intermediate such as the combined reading is processing evidence, not another source or trusted output by itself. | `bookkeeping.targets.mastering.extract` and `master.readings` in [source.yaml](../../../sources/sec.company/source.yaml); the trusted-output boundary is in [LINEAGE.md, What is on the path](../../../skills/data-governance/LINEAGE.md#what-is-on-the-path). |
| Failed processing step | Name matching, combine, prepare or merge is a failable step in the existing example. A failure needs run evidence; configuration alone cannot establish failure or completion, and a downstream output is not shown as completed without that evidence. | [LINEAGE.md, Examples](../../../skills/data-governance/LINEAGE.md#examples) and [How to check](../../../skills/data-governance/LINEAGE.md#how-to-check). No run was inspected or started for this documentation change. |
| Trusted output | The prepared dataset, mastered table and Change Journal are outputs on the path, with the Company subject/product shown only where configured. | [LINEAGE.md, What is on the path and Examples](../../../skills/data-governance/LINEAGE.md#what-is-on-the-path); source `master` declaration in [source.yaml](../../../sources/sec.company/source.yaml). |

The skill index already routes governed-data and lineage questions to Data
Governance; its neighboring rows route business catalog presentation to Data
Catalog and native publication to OpenMetadata. Existing references point
those decisions to their owners, so no index or neighboring skill text needed
to move. The installed Data Governance skill provenance was checked: the
`~/.agents/skills/data-governance` symlink points to a different checkout whose
target is unavailable in this environment. The current repository version is
therefore the source used for this change; the installed copy could not be
compared.

Baseline: `HEAD` and `origin/main` are `4881e8322909888860db576f65730bc4889dc5a4`.
The Data Modeling prerequisite skill change is present on that current main
commit (`adee4305`, merged PR #1978); its ticket still has open closeout items.
No prerequisite ticket was changed.

Validation: `UV_CACHE_DIR=/private/tmp/uv-cache-ticket61 uv run --no-project
--with pytest -- pytest -q -p no:cacheprovider
tests/unit/test_profiling_genericity.py` passed (142 tests), and `git diff
--check` passed. The genericity check constrains skill wording; it does not
validate lineage behavior. No source processing or catalog readback was
performed.
