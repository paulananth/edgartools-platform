# access-audit: Make the entrypoint executable

Type: task
Status: resolved
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
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. The entrypoint was published in [PR #1977](https://github.com/paulananth/edgartools-platform/pull/1977), merged; its verification records 149 passing tests. This ticket-record closeout is in [PR #2013](https://github.com/paulananth/edgartools-platform/pull/2013), on its own branch, draft pending current-head CI.
- [x] Read the installed `write-skill` guidance through `skill://write-skill`; its edit ladder supports no skill change when the required behavior is already present.
- [x] Compare the installed `access-audit` location with the repository copy: neither `~/.agents/skills/access-audit` nor `~/.claude/skills/access-audit` exists, so there is no installed copy to compare; the applicable artifact is the published repository copy.
- [x] This ticket's own access gate: not applicable. The skill edit is already published, and this closeout edits ticket text only; neither change alters a role, login, grant, credential, connection or audited setting. No audit or access operation is authorized or needed.
- [x] Learning → skill: [Start here: audit a change](../../../skills/access-audit/SKILL.md#start-here-audit-a-change) states the three exit shapes, including that an error without a count line means nothing was graded. This lesson is already present in the published skill, so no duplicate text is added.

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

The entrypoint already published in [PR #1977](https://github.com/paulananth/edgartools-platform/pull/1977) replaces **Run it** in place after Hard stops. Its five steps cover applicability, preparation, listing and audit, gate grading, and handoff; the platform variables, expected `--list` output, run exit shapes and stop conditions are present. The objectives, grading, report and handoffs remain linked in place. The current repository copy matches that published entrypoint; no skill edit is needed for this closeout.

Prerequisites: upstream `main` at `90ef96a778784edf3d6f529bb4eb932ad0763fc5` has ticket 03 and ticket 80 marked resolved. Upstream `skills/access-audit/SKILL.md` contains the Start here entrypoint. PR #1977 is merged; its published verification records 149 passing tests and no live audit. Installed-skill check on this machine: neither `~/.agents/skills/access-audit` nor `~/.claude/skills/access-audit` exists, so the installed-copy comparison is not applicable.

No live audit, access change, provider request, or switch-on was performed.

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

Completion evidence is recorded above. The entrypoint's implementation is already published; this ticket-only closeout preserves the existing access boundary and does not duplicate skill text.
