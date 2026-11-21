# data-platform: Measure effectiveness

Type: task
Status: resolved
Priority: P0
Blocked by: 05
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 6 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a new captured source, an already configured source and a restart after a completed phase. Measure time to the first correct next action, wrong routes, repeated setup and unnecessary questions. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md)

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Record the baseline and predeclared improvement targets for first-correct-action response time, wrong routes, repeated setup and unnecessary questions. Baseline and revised results are under [Trial results](#trial-results). (2026-11-21 10:05 ET)
- [x] Compare the revised skill on matching scenarios and attribute waiting/unavailable evidence explicitly. Twelve valid Hatchet trials used matching invented inputs; no tool or operator waiting occurred. (2026-11-21 10:05 ET)
- [x] Report measured gains, regressions, limitations and target outcomes under [Trial results](#trial-results). The response-time target was missed in two scenarios. (2026-11-21 10:05 ET)
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. (2026-11-21 10:09 ET)
- [x] Predeclare revisions, scenarios, metric definitions, targets and protocol before trials. Verified against ticket 05 and the two Data Platform snapshots. (2026-11-21 10:05 ET)
- [x] Operator approved the full twelve-session comparison in this conversation on 2026-11-21. Twelve valid trials ran; six initial attempts with incomplete or mismatched inputs were excluded and replaced. (2026-11-21 10:05 ET)
- [x] Learning → skill: none. The revised text reduced unnecessary questions but missed the response-time target twice; this two-trial-per-cell sample does not justify another wording change. (2026-11-21 10:05 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Answer

The predeclared Hatchet comparison completed: twelve valid Claude Opus sessions, two per scenario per revision. Results and limitations are below. This measures agent behavior when reading the Data Platform documentation; it does not exercise an executable router. No source operation was performed.

### Revisions compared

- **Baseline:** `skills/data-platform/` at `227e1abdb4228b06dbc19dff02f70051062ccecb`, the parent of ticket 01's merge (`git rev-parse f8233ff2^`).
- **Revised:** `skills/data-platform/` at `1b6591cd08e6fafc0f1c6570c9ec8fe2a4b47c1e`; its `SKILL.md` blob was `771ee915306ea5899f38cb8b2060355dd3772259`, matching the revised route at trial time. The baseline blob differs.
- **Exercised copy:** the repository copy only. The installed `~/.agents/skills/data-platform` and `~/.claude/skills/data-platform` both link to a missing target, so no installed copy can be exercised or compared.

### Scenarios and answer key (carried forward)

The answer key is the three operator-approved scenarios from [ticket 05](./05-data-platform-generic-verification.md#answer), unchanged:

| Scenario | Correct first owner | Artifact it must carry | Must not do |
|---|---|---|---|
| New captured source: retained capture with provenance, no `source.yaml` | Data Onboarding, which invokes Data Profiling | Capture location and provenance receipt | Claim a processing qualification |
| Configured source, changed delivery (variant: live-rule change) | Data Operations (variant: Refining Rules) | Source runbook, delivery location, latest Bookkeeping/Journal status (variant: approved configuration, compare report, changed delivery) | Repeat unchanged completed phases or reuse an old proof for a changed input |
| Interrupted load after a completed phase | The owner named by the `## Resume` record's first unfinished action | Matching completed artifacts and the Bookkeeping run id | Redo a phase whose recorded hashes match |

Inputs are invented: a rules folder with or without `sources/<source>/source.yaml`, a delivery manifest, a Bookkeeping status excerpt and a source log with a `## Resume` record. No provider request, load or store is involved.

### Metrics (fixed before any trial)

- **Response time:** elapsed seconds from Claude CLI start to its single JSON answer. Tools were disabled and no operator waited, so no tool/operator wait is included; elapsed time includes CLI/model startup, not pure model compute.
- **Wrong route:** the first owner named is not the key's owner. Counted per trial.
- **Repeated setup:** running a Setup step, profiling or any phase the inputs mark complete. Counted per occurrence.
- **Unnecessary question:** a question to the operator whose answer is in the given inputs or an existing ruling. Counted per occurrence.
- Each trial records its scenario input, skill revision, model output, elapsed response time and outcome; no source command, provider request, store access or load ran.

### Predeclared targets (revised, across all trials)

- Wrong routes: 0.
- Repeated setup: 0 on the configured-source and restart scenarios; not more than baseline on the new-source scenario.
- Unnecessary questions: 0.
- Time to the first correct next action: not more than baseline in any scenario. A rise in any scenario is reported as a regression, even if the other targets are met.

### Protocol

Two trials per scenario per revision: six per revision, twelve valid in all. Each was a fresh Claude Opus session using the same invented prompt and that revision's Data Platform `SKILL.md`, `CONNECTIONS.md` and `RESUME.md` when present. Tools were disabled.

### Trial results

- **Twelve valid Hatchet trials** (response seconds; owner correct / artifact present; repeated setup; unnecessary questions):

| Scenario | Baseline (2 trials) | Revised (2 trials) | Result |
|---|---|---|---|
| New captured source | 19.762, 19.721; mean 19.742; 2/2; 0 repeats; 10 questions | 16.996, 18.756; mean 17.876; 2/2; 0 repeats; 0 questions | Wrong routes 0; timing improved 1.866 seconds on average |
| Configured source, live-rule-change variant | 15.530, 14.259; mean 14.895; 2/2; 0 repeats; 9 questions | 20.549, 16.863; mean 18.706; 2/2; 0 repeats; 0 questions | Wrong routes 0; timing regressed 3.812 seconds |
| Interrupted load with complete `## Resume` record | 18.590, 16.296; mean 17.443; 2/2; 0 repeats; 5 questions | 18.022, 18.235; mean 18.129; 2/2; 0 repeats; 0 questions | Wrong routes 0; timing regressed 0.686 seconds |

- Hatchet baseline trial IDs: `baseline-new-corrected-1`, `baseline-new-corrected-2`, `baseline-configured-1`, `baseline-configured-2`, `baseline-restart-corrected-1`, `baseline-restart-corrected-2`.
- Hatchet revised trial IDs: `revised-new-1`, `revised-new-2`, `revised-configured-1`, `revised-configured-2`, `revised-restart-corrected-1`, `revised-restart-corrected-2`.

Trial inputs were invented and identical within each revision's repeated pair:

- New source: `example.feed` has no baseline `rules/sources/example.feed/source.yaml` or revised `sources/example.feed/source.yaml`; capture `captures/example.feed/delivery-a/`, provenance receipt and manifest hash exist; `edgar-warehouse` is installed, `doctor` is `ok:true`, and no prior run exists.
- Configured source: `source.yaml` exists in that revision's configured rules root; findings and matching policy are approved, a new delivery and compare report exist, and the request is a live matching-rule change. The prompt tests routing from configured state rather than file discovery.
- Restart: a complete `## Resume` record gives matching rules/capture identities, phase `load`, capture/profile/map complete, `run-example-001` units 1-3 verified and unit 4 pending, a Journal receipt for three files, and Data Operations as owner of the first unfinished action.

Targets: wrong routes, repeated setup and revised unnecessary questions were zero. The response-time target (no scenario slower than baseline) was missed for the configured-source and restart scenarios; overall effectiveness targets were not met. Each cell has two trials; treat the timing differences as descriptive, not statistical evidence.

### Limitations

- The first four restart attempts omitted the `## Resume` record's first unfinished owner/action; they were excluded and replaced with two trials per revision using the complete record. Two initial baseline new-source attempts named the revised `sources/` layout rather than baseline `rules/sources/`; they were excluded and replaced with the baseline layout. Six invalid attempts are not included above.
- The temporary result grader first treated hyphenated names such as `data-onboarding` as different from “Data Onboarding” and combined question count with route correctness. Scores above were recomputed from stored raw JSON: owner labels normalized for punctuation; route/artifact correctness, repeated setup and questions scored separately. No trial prompt or answer was altered.
- The elapsed metric is time to the completed single JSON answer, with tools disabled; it includes CLI/model startup. The installed skill copy could not be compared because its symlink target is missing. The open [route capability gap](./gap-data-platform-route.md) means these trials measure an agent reading skill text, not a router.

### Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py`: **142 passed**. This wording/link check does not exercise route behavior. `git diff --check`: passed.
