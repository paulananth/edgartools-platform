# data-platform: Make progress resumable

Type: task
Status: open
Priority: P0
Blocked by: 03
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 4 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record selected source, current phase, owning skill, installed bundle revision and configured connection names. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-profiling, data-onboarding, refining-rules or data-operations.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md)

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Prerequisite: ticket 03 merged. Verified: `HEAD` and `origin/main` are both `c9b1c18f` (#1975, ticket 03), and `git log origin/main` shows #1971, #1972 and #1973 before it. Tickets 03, 08, 13 and 80 are not edited here. (2026-11-20 19:12 ET)
- [x] Specify resume, invalidate and blocked conditions for selected source, current phase, owning skill, installed bundle revision and configured connection names. Done in the [record table](../../../skills/data-platform/RESUME.md#the-record), plus a Next action row. Verified by document review against the rules each condition cites: the Change Journal skip (`CLAUDE.md`, "Loads"), mdm-engineering's carry-forward row, [Source readiness](../../../skills/data-platform/SKILL.md#source-readiness), and the `.installed-by-edgar-warehouse` marker (`install()` and `_tree()` in `edgar_warehouse/bundle.py`). (2026-11-20 19:12 ET)
- [x] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action. Verified by the document trace under [Trace](#trace), case A. It is a reading of the text, not a source run. (2026-11-20 19:12 ET)
- [x] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work. Verified by the document traces under [Trace](#trace), cases A, B and C. They show what the text decides. They do not show that any code enforces it: the resume decision is made by the reader, and only the Change Journal's file skip is enforced by code (not exercised here). (2026-11-20 19:12 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. Checks ran (see [Validation](#validation)). Not committed, pushed or opened as a PR in this session (the session's instructions).
- [ ] Read the installed `write-skill` guidance (`~/.agents/skills/write-skill/SKILL.md`): not read. The session's permissions refused both a direct read and loading it as the `write-skill` skill.
- [ ] Compare the installed `data-platform` copy with the repository copy: not done. Both `~/.agents/skills/data-platform` and `~/.claude/skills/data-platform` link to `~/.local/share/edgartools/skill-source/skills/data-platform`, and the sandbox refused a `diff` outside this worktree. The repository copy is the one changed.
- [ ] ~~Add the `## Resume` section to data-onboarding's and refining-rules' log instructions~~ deferred to tickets 22 and 34 (their skills' resume steps): this ticket defines the record in Data Platform and does not edit another skill's procedure.
- [ ] Learning → skill: proposed lesson, in [Resume](../../../skills/data-platform/RESUME.md#resume): a resume record holds hashes and names, never a copy of unit state, so Bookkeeping and the Change Journal stay the only authority for runs. Not ticked until the change is published and reviewed.

## Changes

- `skills/data-platform/RESUME.md` (new, 70 lines). The record is one `## Resume` section in the source's existing
  log, either `onboarding-log.md` or `refining-log.md`. For a run it holds the run id alone. A table gives each of the
  six fields (source, phase, owning skill, installed bundle revision, configured connection names, next action) with
  what to record and when it is reused, reopened or blocked. Then come the five resume steps, the three rules
  (unchanged inputs repeat nothing, changed inputs reuse no proof, unfinished work stays visible) and an invented
  example record.
- `skills/data-platform/SKILL.md`: two pointers to it, with the line count unchanged at 499. One is in Start here,
  step 1. The other replaces the "Restart after a completed phase" routing example. The whole `skills/` folder ships
  in the bundle (`packages/data-skill/pyproject.toml`, `"../../skills"` under `force-include`), so the new file is
  installed with the skill.

## Trace

Both cases are readings of `RESUME.md` and `SKILL.md`, not runs. The source `example.feed` and its values are
invented. Start from the [example record](../../../skills/data-platform/RESUME.md#example-record): profile complete,
interrupted in map, part 1, with identifiers mapped and fields 13 to 20 not yet.

**Case A, nothing changed.** Step 2 checks the fields in table order. Source: the name matches, the rules identity
is still `none`, and the manifest hash matches. Phase: both profile artifacts hash as recorded. Owning skill: no
`source.yaml` yet, so the Decisions table still gives data-onboarding. Bundle revision: both skill markers match, and so does the engine
ref recorded at Setup. Connections: duty none, every store `not set`. Everything is reused, so step 3 gives the recorded next
action at its first unchecked item: **data-onboarding, map, part 1, fields 13 to 20**. Profiling does not run again,
and `REPORT.md` and `findings.yaml` are handed on as they are.

**Case B, another delivery selected.** A later delivery, `captures/example.feed/2026-02`, is now the selected
capture, so the capture and its manifest sha256 differ from the record. The Source row reopens every phase whose
evidence used the capture: profile, and map after it. The earlier `REPORT.md` and
`findings.yaml` stay where they are, marked reopened with the field that reopened them, and are not reused. Step 3
gives the earliest reopened phase's first step: **profile, part 1, owner data-profiling** (by way of data-onboarding,
which invokes it). The map checklist is not ticked from the old profile.

**Case C, the recorded capture no longer hashes as recorded.** Captured files never change, so this is not a new
input. The Source row blocks the resume, and the defect is reported to its owner. Nothing is reused and nothing is
reopened. A missing manifest blocks the same way.

## Answer

Another session can resume from one `## Resume` section in the source's existing onboarding or refining log. The
section holds the source's rules and capture hashes, each completed artifact's path and sha256, the owner, the
installed bundle revision, the duty and the connection variable names (never values), and the next action as a
checklist. A field that matches is reused. A changed rules identity, another selected delivery or a changed revision
reopens that phase and every later one, and the old artifacts are kept but not reused. A missing input, or a recorded
capture that no longer hashes as recorded, blocks the resume. An unreadable revision, or an engine ref never
recorded, counts as changed. A Bookkeeping run keeps its frozen runtime, so a new engine ref does not reopen it. Run state stays in
Bookkeeping and the Change Journal. Not resolved: publication, the `write-skill` read, the installed-copy comparison
and the learning remain open.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py`: **150 passed**. They check skill wording, the line limit, genericity and the paths the guides name. They do not exercise resume behaviour.
- A no-import link and anchor check over `SKILL.md` and `RESUME.md`: 75 relative links, 0 broken.
- `bundle.py`'s `_COMMAND` pattern over `SKILL.md` before and after: the same 18 command lines. `RESUME.md` names `bookkeeping status`, `doctor`, `load` and `skill install`, which `SKILL.md` already names. This shows the resolver sees no new command group. It does not run the resolver.
- `git diff --check`: clean.
- `uv run --no-project --with pytest --with pyyaml --with sqlalchemy --with 'psycopg[binary]' -- pytest -q -p no:cacheprovider tests/unit/test_skill_bundle_portability.py tests/unit/test_role_skills.py tests/unit/test_rules_skill_commands.py`: **10 passed, 2 failed**. `test_skill_commands_and_links_resolve_without_checkout` and `test_role_skills_name_registered_commands` failed on import with `ModuleNotFoundError: No module named 'source_contract'`, because the Rust engine is not built in this worktree (no `.venv/bin/pytest`). Command resolution for `RESUME.md` is unproven here; CI runs it.
- Not run: `edgar-warehouse doctor` (not installed).

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
