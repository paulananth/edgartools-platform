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

- The current `origin/main` contains the merged prerequisite skill changes, including tickets 03, 04, 08, 13, 14, 80 and 81. Installed-skill provenance could not be compared: `~/.agents/skills/data-platform` points to a missing target. Only the repository skill was reviewed.
- The operator approved the three scenarios in this conversation before any scenario code. No scenario tests or source load were run: the route exists only as skill text, so these cases have no executable generic path. The capability gap is linked above; no behavior is claimed or marked PASS.

### Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py`: **142 passed**. This check scans documentation wording; it does not exercise routing, load or resume behavior.
- Scenario tests and source load: not run because no executable route exists. This is the capability gap, not pending scenario approval.
- Draft PR #1983 publishes the scenarios and gap. Its prior 12-check CI was on an older base; refresh CI on the current base before marking ready.
