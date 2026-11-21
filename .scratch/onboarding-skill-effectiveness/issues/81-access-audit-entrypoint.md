# access-audit: Make the entrypoint executable

Type: task
Status: open
Priority: P1
Blocked by: 03, 80
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [access-audit](../../../skills/access-audit/SKILL.md)
Step: 3 of 6
Skill dependencies: data-platform
Applicability: Review the skill or access changes being finalized; run only applicable read-only platform checks.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: platform applicability, read-only audit connections, changed roles and existing control objectives. Outputs: PASS, FAIL and NOT_TESTED evidence with a coverage matrix and separate remediation references. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/access-audit/SKILL.md: Hard stops, Objectives, The gate before finalising a skill role or login. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [access-audit: Reconcile shared rules](./80-access-audit-consistent-rules.md)

Priority rationale: Independent access evidence is cross-cutting; remediation is separate.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Produce an entrypoint that consumes platform applicability, read-only audit connections, changed roles and existing control objectives and yields PASS, FAIL and NOT_TESTED evidence with a coverage matrix and separate remediation references; verified by document review of [Start here: audit a change](../../../skills/access-audit/SKILL.md#start-here-audit-a-change), its exit shapes and output lines matched to `main()` in `skills/access-audit/scripts/access_audit.py` and the adapters' `configured()`, `collect()` and `principals()`. (2026-11-20 19:10 ET)
- [x] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail; verified by a no-import link check (22 relative links and their anchors resolve), by `bundle.py`'s `_CHECKOUT_ONLY` pattern over the edited file (no match), by matching every flag the text names (`--list`, `--repo`, `--platform`, `--principal`, `--json`, `--as-admin`) to `main()`'s parser, and by one read-only `--list` run (see [Validation](#validation)). Hard stops stay first and unchanged. (2026-11-20 19:10 ET)
- [x] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure; verified by the document trace under [Trace](#trace). It is a reading of the text, not a live audit. (2026-11-20 19:10 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. The checks ran (see [Validation](#validation)). Nothing was committed, pushed or opened as a PR in this session.
- [ ] Read the installed `write-skill` guidance (`~/.agents/skills/write-skill/SKILL.md`). It was not read: the session's permissions refused both a direct read and loading it as the `write-skill` skill.
- [ ] Compare the installed `access-audit` copy with the repository copy. Not compared: `readlink` on `~/.agents/skills/access-audit` and `~/.claude/skills/access-audit` exited 1, and listing those paths was refused, so whether an installed copy exists is unknown. `access-audit` is not among this session's available skills. The repository copy is the one changed.
- [ ] This ticket's own access gate: not applicable. The change edits skill text only and adds or alters no role, login, grant, credential, connection or audited setting. Ticked with publication.
- [ ] Learning → skill: proposed lesson for [Start here: audit a change](../../../skills/access-audit/SKILL.md#start-here-audit-a-change). An entrypoint names each exit shape a command can produce, from its code, and says which one means "nothing was graded". Here, an error with no count line is NOT_TESTED, never a FAIL to fix. Not ticked until the change is published and reviewed.

## Changes

- `skills/access-audit/SKILL.md`: **Run it** becomes **Start here: audit a change**, in the same place after Hard stops. It holds
  the inputs and output and five steps: decide applicability, prepare, list then audit, grade against the gate, hand off. It
  states the expected `--list` output and the three exit shapes of a run, then the stop conditions. The platform table gains a
  `Set` column (each platform's variable or file). Three corrections came from the code:
  - The commands pass `--repo ../..`, because CHG reads `.scratch/` and `infra/` under `--repo` (default `.`), and the
    skill-relative path `scripts/access_audit.py` runs from the skill folder.
  - `--principal` is stated as Snowflake only (`run_from_evidence`).
  - `reader.env` is sourced in a command-scoped subshell with tracing off ([Connections](../../../skills/data-platform/CONNECTIONS.md)).
- The handoffs row about audit logins now links to Start here. No other heading changed, and no file outside `.scratch/` links to
  an `access-audit/SKILL.md#` anchor.
- No split was proposed. The file is 168 lines, and Objectives, Add a platform, Rating and report and Limits are reached by link
  or read in order.

## Trace

A change that adds a connection limit to a PostgreSQL login. This is a reading of the text, not a run. Files opened, in order:
`skills/access-audit/SKILL.md` (Hard stops, Start here, the gate, the handoffs table) and nothing else.

1. Applicability: the change alters an audited setting on one platform, `postgres`. Not Snowflake or AWS, so
   `aws-snowflake-operations` is not opened.
2. Prepare: a Python where `edgar_warehouse` imports. From the skill folder, `--repo ../..`. The PostgreSQL row names the stores
   folder's `reader.env`. `CONNECTIONS.md` is not needed: the row and the subshell form are enough.
3. `--list` must name `postgres`. The run is `--platform postgres` with no `--principal`, because the postgres adapter names no
   principals. A connection limit on a platform login is outside the count (the Objectives note), so a FAIL on `CST.postgres`
   names the logins that have no limit.
4. Gate: with `CST.postgres` failing, the change is not finalised until it is fixed or carries a signed acceptance.
   `ROT.postgres` and `REV.postgres` are NOT_TESTED, and both are named as not tested.
5. Hand off: the "Fixing a PostgreSQL role guard" row sends the failing CST control to Data Operations' role guards
   (`HOSTED-LOADS.md#before-a-load-starts`). After the guards are applied, re-run step 3 on `postgres`. Stop there.

Not opened: `CONNECTIONS.md`, `HOSTED-LOADS.md` (only named as the handoff target), `aws-snowflake-operations`, and the adapters.
No other skill's procedure is repeated.

## Answer

The shortest sufficient entrypoint replaces Run it, in its place right after Hard stops. It holds the inputs and output, five
steps, the per-platform variables, one command block, the expected `--list` output and the three exit shapes, and the stop
conditions. Objectives, grading, report and handoffs stay where they are, reached by link. Not resolved: publication, the
`write-skill` read, the installed-copy comparison, the not-applicable gate record and the learning remain open.

Provenance: the branch head is `c9b1c18f`, which is `origin/main` (fetched this session). That covers ticket 03 (#1975,
`c9b1c18f`), ticket 08 (#1972, `d2879db5`), ticket 13 (#1971, `576904f0`) and ticket 80 (#1973, `750c06f2`), as shown by
`git log origin/main`. Their ticket files are not edited here.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py`:
  **149 passed**. These check skill wording, the line limit, genericity and the paths named by `CLAUDE.md` and `AGENTS.md`. They do
  not exercise the audit.
- A no-import check over `skills/access-audit/SKILL.md`: 22 relative links and their anchors resolve. `bundle.py`'s `_CHECKOUT_ONLY`
  pattern has no match.
- `git diff --check`: clean.
- `python3 scripts/access_audit.py --list --repo ../..`, run from `skills/access-audit/` with no package environment: exit 1 with
  `ModuleNotFoundError: No module named 'edgar_warehouse'`, raised from `postgres.configured()`. This is the evidence for step 2's
  prerequisite. No platform was read.
- `uv run --no-project --with pytest --with pyyaml --with sqlalchemy --with 'psycopg[binary]' -- pytest -q -p no:cacheprovider tests/unit/test_skill_bundle_portability.py tests/unit/test_access_audit.py`:
  **50 passed, 1 failed**. `test_access_audit.py` passed; it tests the grading code, which is unchanged, not this text.
  `test_skill_commands_and_links_resolve_without_checkout` failed on import with `ModuleNotFoundError: No module named 'source_contract'`.
  The Rust engine is not built in this worktree (no `.venv/bin/pytest`), so the failure says nothing about the skill text, and
  command resolution is still unproven here. CI runs it.
- Not run: a live audit on any platform. The ticket's own change touches no access, and no audit connection was configured.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
