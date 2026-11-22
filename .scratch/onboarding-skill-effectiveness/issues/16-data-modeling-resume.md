# data-modeling: Make progress resumable

Type: task
Status: claimed
Priority: P0
Blocked by: 04, 10, 15
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 4 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record part decisions, supporting findings, unresolved semantics and downstream contracts affected. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-onboarding and data-quality; data-catalog consumes the resulting meaning.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-profiling: Make progress resumable](./10-data-profiling-resume.md); [data-modeling: Make the entrypoint executable](./15-data-modeling-entrypoint.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Specify resume, invalidate and blocked conditions for part decisions, evidence, unresolved semantics and downstream contracts in the existing source log's `Phase` and `Next action` fields. (2026-11-22 12:21 ET)
- [x] Trace a staged interruption across two invented parts and identify the first unfinished action without rerunning completed work. (2026-11-22 12:21 ET)
- [x] Show unchanged evidence reuses only its part decisions; changed evidence reopens the affected part and dependent handoff; unapproved or missing evidence blocks back to Data Profiling. (2026-11-22 12:21 ET)
- [ ] Publish the rebased scoped change in PR #2027 and pass current-head CI. The local branch is rebased onto latest `origin/main` (`505dc839`); the remote PR still points to pre-rebase head `ec61d4e27a`. CI on the updated head is pending.
- [x] Learning → skill: `Workflow` now routes resume through the shared source log, preserving part-level decisions and invalidation. (2026-11-22 12:21 ET)

## Answer

Data Modeling resumes part decisions from the shared source log, reusing only matching approved evidence and reopening affected downstream handoffs. The documented trace covers unchanged, changed and blocked evidence without source data or test code. The branch was rebased onto latest `origin/main` (`505dc839`); keep PR #2027 draft until the updated head's CI passes.

Documentation trace using invented part names only:

| Saved state | Resume result |
|---|---|
| `part_alpha` has a completed decision artifact and approved findings hash; `part_beta` has an unresolved identity-versus-lookup question and an unwritten Dataset Contract. The shared record lists the two parts and the next action for `part_beta`. | With unchanged source/rules/findings identities, reuse `part_alpha` and resume at `part_beta`'s first unchecked decision; no profile or decision is repeated for `part_alpha`. |
| Only `part_beta`'s approved findings identity changes. | Reopen `part_beta` and its dependent Data Onboarding contract; retain `part_alpha` if its evidence is unchanged. Resume at the first unchecked `part_beta` action. |
| Findings are draft/unapproved or a required identifier measurement is missing. | Block `part_beta` and hand back to Data Profiling; do not create or reuse a model decision. |

The installed `data-modeling` skill is unavailable (`skill://data-modeling` unknown; `gstack-skill-bill data-modeling` found no installed copy). This edit uses the repository skill. Before/after size: 35,513→36,288 bytes. No source, provider or store was accessed; no test code was added.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py`: **145 passed in 0.22s** (2026-11-22 12:22 ET). This checks generic skill wording, not live resume behavior.
- No guide was edited, so `test_guides_name_existing_paths.py` was not applicable.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while any acceptance item remains open.