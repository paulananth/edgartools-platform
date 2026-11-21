# data-modeling: Make the entrypoint executable

Type: task
Status: open
Priority: P0
Blocked by: 03, 09, 14
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 3 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: profiling findings, CONTEXT.md, existing kind definitions and published reference sets. Outputs: a model decision per part with identity versus lookup choices and destination rationale. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [data-profiling: Make the entrypoint executable](./09-data-profiling-entrypoint.md); [data-modeling: Reconcile shared rules](./14-data-modeling-consistent-rules.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Produce an entrypoint that consumes approved profiling findings, `CONTEXT.md`, existing kind definitions and published reference sets and yields one model decision per part with identity versus lookup choices and destination rationale; verified by document review against the current `data-profiling` handoff and `data-modeling` rules. The genericity check passed (142 tests); this checks generic language, not routing behavior. (2026-11-20 19:51 ET)
- [x] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail; verified by checking all 38 local links and anchors in `skills/data-modeling/SKILL.md`, matching `context mdm-kinds` to `edgar_warehouse/context.py`, `rdm list` and `rdm describe` to `edgar_warehouse/rdm/cli.py`, and review that Hard stops remain before the entrypoint and optional references are linked. The commands were inspected in code, not run against stores. (2026-11-20 19:51 ET)
- [x] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure; verified by the reading trace under [Trace](#trace). This is a document trace, not a live modeling run. (2026-11-20 19:51 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: `Start here: decide one part` keeps published reference lookups on `rdm list` and `rdm describe`, whose outputs expose the meaning and version needed for a model decision; verified against the command descriptions and response construction in `edgar_warehouse/rdm/cli.py`. (2026-11-20 19:51 ET)

## Trace

For a part whose approved findings identify an existing master kind:

1. Read its class tests, new-kind tests, key and identifier pairs from the approved `findings.yaml`; use `REPORT.md` to interpret those measured results. Read `CONTEXT.md` for the platform terms.
2. Run `edgar-warehouse context mdm-kinds` and inspect the kind's `rules/merge/kinds/<kind>.yaml` Identifier Contract. The first returns the existing kind codes and definitions; the contract shows which namespaces decide identity.
3. Decide that identifiers declared by the contract can match and that other identifiers remain lookup-only. Record the part's class, master kind, destination rationale, key and time roles from the approved evidence.
4. Hand the decision and findings to Data Onboarding for a new feed, which owns its configuration.

This routine path needs no code-set, Gold, dimensional or temporal reference and repeats neither profiling nor onboarding procedure. The trace follows the entrypoint and its handoff table; it is not a store query or a proof on source data.

## Answer

The shortest sufficient entrypoint is `Start here: decide one part`, placed after Hard stops. It checks approved evidence, reads the current kind and published code-set context with supported commands, writes the model decision per part, and names the handoff owner and stop conditions. Decision rules stay in the existing sections; Gold, dimensional and temporal material remains discoverable through conditional links.

Provenance: the ticket's prerequisite skill changes are present on `origin/main`: ticket 03's entrypoint commit `c9b1c18f` is an ancestor, as are ticket 09 / PR #1980 commit `2bcbbda62` and ticket 14 / PR #1978 commit `adee43054`. Their local `Status` lines were not edited. The repository skill at `origin/main` was used as the baseline. No installed `data-modeling` skill exists at `~/.agents/skills/data-modeling` or `~/.claude/skills/data-modeling`; `gstack-skill-bill data-modeling` also returned `SKILL_NOT_FOUND`. The installed `write-skill` guidance was read at `~/.agents/skills/write-skill/SKILL.md`.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py`: **142 passed**. This repository check enforces generic skill/spec wording; it does not exercise modeling decisions or behavior.
- Local Markdown paths and anchors in `skills/data-modeling/SKILL.md`: **38 checked, 0 errors**.
- Supported command review: `context mdm-kinds` maps to the registered `edgar-warehouse context` parser and RDM context reader; `rdm list` and `rdm describe` are registered in `edgar_warehouse/rdm/cli.py`. Commands were not run against a connected store.
- `git diff --check`: clean.
- Not run: tests that import the engine, live commands, or source-data modeling proof; this is a documentation-only entrypoint change and no store access or source run was authorized.
- Not run: `bash scripts/dev/overlap_guard.sh`; no commit or push is authorized.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
