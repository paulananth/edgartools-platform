# data-platform: Make the entrypoint executable

Type: task
Status: open
Priority: P0
Blocked by: 02
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 3 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: source readiness, the skill index and private connection-variable names. Outputs: one selected next action, its owner and the required environment checks. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md)

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Produce an entrypoint that consumes source readiness, the skill index and private connection-variable names and yields one selected next action, its owner and the required environment checks; verified by document review of [Start here: route the work](../../../skills/data-platform/SKILL.md#start-here-route-the-work), its `doctor` expectations matched line by line to `edgar_warehouse/bundle.py` (`doctor()`, `_store()`, `_print()`) and its configured-source test to `edgar_warehouse/rules/files.py` (`EDGAR_RULES_ROOT`, else the bundled rules; `sources/<name>/source.yaml`). (2026-11-20 18:41 ET)
- [x] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail; verified by a no-import link check (65 relative links and every `#anchor` in `SKILL.md` resolve; the two `data-profiling` anchors also exist on `origin/main`), by matching the one command the new text names, `edgar-warehouse doctor`, to `add_parser("doctor")` in `edgar_warehouse/bundle.py`, by running `bundle.py`'s `_COMMAND` pattern over the old and new `SKILL.md` (the same command lines, none added or removed), and by document review that Hard stops stay first and every optional reference stays linked. `edgar-warehouse doctor` itself did not run (not installed), and the two command-resolution tests stopped on import (see [Validation](#validation)). (2026-11-20 18:41 ET)
- [x] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure; verified by the document trace under [Trace](#trace). It is a reading of the text, not a source run. (2026-11-20 18:41 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. Checks ran (see [Validation](#validation)); not committed, pushed or opened as a PR in this session.
- [ ] Read the installed `write-skill` guidance (`~/.agents/skills/write-skill/SKILL.md`): not read. The session's permissions refused a direct read of the file and loading it as the `write-skill` skill.
- [ ] Learning → skill: proposed lesson in [Start here: route the work](../../../skills/data-platform/SKILL.md#start-here-route-the-work): an entrypoint states each check's expected output from the command's own code (doctor probes four stores, `not set` passes), so a reader can tell a pass from a stop without opening another file. Not ticked until the change is published and reviewed.

## Changes

- `skills/data-platform/SKILL.md`: a **Start here: route the work** section right after Hard stops: inputs, the
  output, five steps (find the state, pick the owner, name the duty, run `doctor` with its expected output, hand
  off) and the stop conditions. The route-output paragraph and the routing examples in **Decisions, artifacts and
  handoffs** were shortened to what Start here does not say; that heading and every inbound anchor are unchanged.
  The file is 499 lines (limit: under 500).
- No split was proposed: `CONNECTIONS.md`, `STORES.md`, `READING.md` and the other references already hold the
  optional detail, and Parse, Master and Setup are marked reference in **The flow**.

## Trace

A new captured data set: files retained with a provenance receipt, no rules for it yet. The walk assumes
`edgar-warehouse` is installed. On this machine it is not (`which edgar-warehouse`: not found), so here step 1
alone gives the one next action: Setup, step 1, owner Data Platform, and stop. Files opened, in order:
`skills/data-platform/SKILL.md` (Hard stops, Start here, the Decisions table) only.

1. Find the state: the rules folder (`EDGAR_RULES_ROOT`, else the bundle's copy) has no
   `sources/<source>/source.yaml`, so the source is new.
2. Pick the owner: the "Capture inventory, profile findings…" and "New feed/domain decisions…" rows both send a
   new data set to Data Onboarding (which invokes Data Profiling). One owner, so no stop.
3. Duty: none; reading captured files needs no store login. `CONNECTIONS.md` did not need to be opened.
4. `doctor`: expected `"ok": true` with all four stores `not set`, which passes.
5. Hand off the capture location and provenance receipt to Data Onboarding's
   [The files are the rules](../../../skills/data-onboarding/SKILL.md#the-files-are-the-rules); stop there.

Not opened: `READING.md`, `COMBINING.md`, `STORES.md`, `LOCAL-TESTING.md`, `HOSTED-MIRRORING.md`,
`FINAL-TABLES.md`, `SINGLE-DATABASE-ICEBERG.md`, `ROOT-CAUSE.md`, and no data-onboarding or data-profiling procedure.
The route grants no provider request: if the field definitions sit only in provider documentation, that is a Hard
stop for Data Onboarding's discover step to raise.

## Answer

The shortest sufficient entrypoint is one section placed directly after Hard stops: its inputs and output, five
steps and the stop conditions, with `doctor`'s expected output stated from its code. Everything else in the skill
stays reference, reached by link. Not resolved: publication and the learning remain open.

Provenance: the branch is based on `30ae0e7b`, which contains ticket 02's merge `e166fa56`, ticket 07's `6c5c5393`
and ticket 79's `30ae0e7b` (checked with `git merge-base --is-ancestor`). `origin/main` has since moved to
`576904f0` (#1971). `git diff --stat HEAD origin/main` touches no `skills/data-platform/` file, and
`origin/main`'s `skills/data-platform/SKILL.md` is 496 lines, the same as this branch's base. So this change still
gives 499 lines on top of it. `~/.agents/skills/data-platform` and `~/.claude/skills/data-platform` both link
(`readlink`) to `~/.local/share/edgartools/skill-source/skills/data-platform`. The session's permissions refused
reading that target, so no installed copy was compared. The repository copy is the one changed.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py`: **149 passed** (one failure at 501 lines on the first draft, fixed). These check skill wording, the line limit, genericity and the paths `CLAUDE.md`/`AGENTS.md` name; they do not exercise routing.
- A no-import link check over `skills/data-platform/SKILL.md`: 65 relative links and their anchors resolve.
- `bundle.py`'s `_COMMAND` pattern over `git show HEAD:skills/data-platform/SKILL.md` and the edited file: the same
  command lines, none added or removed. It shows the resolver sees no new command. It does not run the resolver.
- `git diff --check`: clean.
- `uv run --no-project --with pytest --with pyyaml --with sqlalchemy --with 'psycopg[binary]' -- pytest -q -p no:cacheprovider tests/unit/test_skill_bundle_portability.py tests/unit/test_role_skills.py tests/unit/test_rules_skill_commands.py`: **10 passed, 2 failed**. `test_rules_skill_commands.py` passed. `test_skill_commands_and_links_resolve_without_checkout` and `test_role_skills_name_registered_commands` failed on import with `ModuleNotFoundError: No module named 'source_contract'`: the Rust engine is not built in this worktree (no `.venv/bin/pytest`). These failures come from the environment and say nothing about the skill text. Command resolution is still unproven here; CI runs it.
- Not run: `edgar-warehouse doctor` (not installed; its CI copy is `tests/engine/test_data_skill_bundle_postgres.py`).

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
