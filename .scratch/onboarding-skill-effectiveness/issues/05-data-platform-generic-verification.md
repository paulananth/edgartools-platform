# data-platform: Specify generic verification

Type: task
Status: open
Priority: P0
Blocked by: 04
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 5 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: a new captured source, an already configured source and a restart after a completed phase.

Required observable proof: route a new source, a changed source and an interrupted load to their distinct owners without redoing completed phases. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md)

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation. The three scenarios are under Answer. The operator approved them in this session on 2026-11-20. (2026-11-20 19:43 ET)
- [x] Use the existing generic path to route a new source, a changed source and an interrupted load to their distinct owners without redoing completed phases. No such path exists. The route is skill text only. Linked [gap-data-platform-route](./gap-data-platform-route.md) instead of adding a router or a text-only test. (2026-11-20 19:43 ET)
- [x] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof. Outcome: no behavior was stored. Limitation: there is no executable route. This is not a PASS. (2026-11-20 19:43 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: none; this documentation-only proposal establishes no verified reusable lesson to add to the skill. Verified by reviewing the scope and current evidence below. (2026-11-20 19:40 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Answer

### Proposed scenarios — approval required before test code

These scenarios follow [Start here: route the work](../../../skills/data-platform/SKILL.md#start-here-route-the-work), [Source readiness](../../../skills/data-platform/SKILL.md#source-readiness), and [Resume](../../../skills/data-platform/RESUME.md). Inputs are invented and supplied as configuration/retained artifacts; the proposal adds no source-specific runtime logic.

1. **New captured source.** Given a retained capture with provenance evidence and no `sources/<source>/source.yaml`, when the common entry route checks configuration and run evidence, then it hands the capture location and provenance receipt to Data Onboarding, which invokes Data Profiling; no processing qualification is claimed before the owning phase records it.
2. **Configured source with changed delivery or live rules.** Given a configured source and retained prior run evidence, when the selected delivery changes, then the route hands the source runbook, delivery location and latest Bookkeeping/Journal status to Data Operations. Given instead a live-rule change and its approved configuration and compare report, then it hands those artifacts and the changed delivery to Refining Rules. The route must not repeat unchanged completed phases or treat a changed input's old proof as current.
3. **Interrupted load after completed phase.** Given a source log with a `## Resume` record, matching hashes/revisions for completed phases and a retained Bookkeeping run with verified completed units, when processing resumes, then it reuses the matching completed artifacts and gives the first unfinished action to its named owner; changed inputs reopen affected downstream phases, and the run state remains authoritative in Bookkeeping/Change Journal.

### Evidence and limitations

- The local `origin/main` ref contains prerequisite commit `4881e8322909888860db576f65730bc4889dc5a4` (ticket 04) and `adee430549b843ce93e8b0a96f306700fc3d8a1e` (ticket 14); both are ancestors of that ref. The log also contains ticket 03 (`c9b1c18f`), ticket 13 (`576904f0`), ticket 08 (`a5624b18`), ticket 80 (`d3de34ad`) and ticket 81 (`4da40b6a`). This verifies the review's prerequisite claims against the local ref; fetching a newer ref was unavailable because Git could not write the shared worktree's `FETCH_HEAD`.
- Installed-skill provenance: `~/.agents/skills/data-platform` is a symlink to `~/.local/share/edgartools/skill-source/skills/data-platform`, but that target directory does not exist. Therefore the installed copy could not be read or compared; only the repository skill at [SKILL.md](../../../skills/data-platform/SKILL.md) was reviewed.
- `~/.agents/skills/write-skill/SKILL.md` was read. Its installed provenance is a symlink to `~/.agents/skills/gstack/write-skill/SKILL.md`. The `write-skill` guidance concerns authoring skills; this ticket proposes verification scenarios and does not justify changing skill wording before behavior is established.
- No scenario approval is recorded in this task instruction. No test/scenario code or load was run. Consequently there are no stored behavior outcomes, and the routing and resume claims remain unqualified by executable behavioral evidence. This proposal is not a PASS and does not establish runtime enforcement.

### Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py`: **142 passed**. This repository check scans skills and specifications; the changed ticket is outside its scope. It does not validate routing, load or resume behavior.
- Not run: scenario tests and source load, pending scenario approval and outside this request's authorized scope.
- Not run: publication; this handoff explicitly forbids commit, push and PR creation.
