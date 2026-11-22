# data-governance: Make the entrypoint executable

Type: task
Status: open
Priority: P1
Blocked by: 03, 15, 62
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-governance](../../../skills/data-governance/SKILL.md)
Step: 3 of 6
Skill dependencies: data-modeling
Applicability: Every source's governed outputs and lineage claims.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: source declarations, target contracts, step checks and independently verified outputs. Outputs: a governed lineage contract and explicit coverage or evidence gaps. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/data-governance/SKILL.md: What is governed, Completion; LINEAGE.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [data-modeling: Make the entrypoint executable](./15-data-modeling-entrypoint.md); [data-governance: Reconcile shared rules](./62-data-governance-consistent-rules.md)

Priority rationale: Governed output and lineage meaning precede catalog presentation.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Produce an entrypoint that consumes source declarations, target contracts, step checks and independently verified outputs and yields a governed lineage contract and explicit coverage or evidence gaps; verified by the new [Start here section](../../../skills/data-governance/SKILL.md#start-here-trace-one-configured-target), which maps configured input and evidence to a scoped graph, gaps and owners. (2026-11-21 19:25 ET)
- [x] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail; verified by resolving each new relative link and confirming owner anchors, checking `rules check --source`/`--root` against `edgar_warehouse/rules/cli.py` and its JSON output against `files.py`, and confirming Shared rules remains before Start here. (2026-11-21 19:25 ET)
- [x] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure; verified by tracing the SEC Company mastering contract and its neutral lineage example under [Trace](#trace), then handing business meaning to Data Catalog, publication/readback to the selected destination, and missing run evidence to Data Operations. This is a document trace, not a source run. (2026-11-21 19:25 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: validate the source contract offline, but keep configuration success distinct from run completion and destination state; recorded in [Start here](../../../skills/data-governance/SKILL.md#start-here-trace-one-configured-target). (2026-11-21 19:25 ET)

## Trace

The applicable example is SEC Company mastering. The trace follows [Start
here](../../../skills/data-governance/SKILL.md#start-here-trace-one-configured-target),
the required [LINEAGE.md example](../../../skills/data-governance/LINEAGE.md#examples)
and its [source contract](../../../sources/sec.company/source.yaml). The
contract declares the `mastering` target with a captured extract, prepare and
merge; the lineage example identifies SEC submissions and the ticker reference,
the material Name Matching control, declared checks on failable steps and the
trusted prepared/mastered outputs. The Company domain and Company master
product stay only where the lineage contract supports them. The folder also
contains `quality.yaml`.

When needed, Start here validates configuration with
`edgar-warehouse rules check --source sec.company`; the implementation returns
the source key as `ok` or `refused`, and does not establish execution. No
Bookkeeping run was read for this document trace, so the proposed path does not
claim observed completion. No catalog was written or read back. Governance
hands the neutral graph and gaps to Data Catalog for meaning/presentation and
the selected destination skill for publish/readback; Data Operations supplies
verified run evidence if completion is in scope. No modeling, onboarding or
catalog/destination procedure is repeated; the trace ends at existing owner
handoffs.

## Answer

The shortest sufficient route is [Start here: trace one configured
target](../../../skills/data-governance/SKILL.md#start-here-trace-one-configured-target).
It identifies the active source and target contracts and checks, offers one
verified offline configuration command, converts the applicable contract into
the neutral graph, distinguishes intended edges from run and destination
evidence, names gaps, and hands each remaining duty to its owner. The existing
[LINEAGE.md](../../../skills/data-governance/LINEAGE.md) remains the detailed
contract; no split or duplicate procedure is needed.

**Provenance.** This worktree is based on `origin/main` at `a3d2a617`. The
repository skill matched that baseline before editing. Both installed skill
links (`~/.agents/skills/data-governance` and `~/.claude/skills/data-governance`)
point to a different checkout whose target is unavailable; the installed copy
could not be compared. Prerequisites 03, 15 and 62 are resolved on this
baseline; their files were not changed.

## Validation

- Reviewed the command parser and handler in `edgar_warehouse/rules/cli.py`
  and output/check behavior in `edgar_warehouse/rules/files.py`; the documented
  JSON key/value reflects the implementation. The command was not run.
- Verified new skill links point to repository paths and the named owner
  sections exist. The existing `LINEAGE.md` link remains required before the
  entrypoint; Shared rules and its scenario-authorization stop remain above it.
- No source run, provider request, test scenario, catalog publication or native
  readback was performed. No local tests were run.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
