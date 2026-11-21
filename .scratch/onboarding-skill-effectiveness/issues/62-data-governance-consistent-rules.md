# data-governance: Reconcile shared rules

Type: task
Status: resolved
Priority: P1
Blocked by: 02, 14, 61
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-governance](../../../skills/data-governance/SKILL.md)
Step: 2 of 6
Skill dependencies: data-modeling
Applicability: Every source's governed outputs and lineage claims.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: a governed lineage contract and explicit coverage or evidence gaps.

Start from skills/data-governance/SKILL.md: What is governed, Completion; LINEAGE.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [data-modeling: Reconcile shared rules](./14-data-modeling-consistent-rules.md); [data-governance: Define one responsibility](./61-data-governance-responsibility.md)

Priority rationale: Governed output and lineage meaning precede catalog presentation.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition; verified by reviewing `CLAUDE.md`, tickets 02/14/61, the governance skill and `LINEAGE.md` under [Inventory](#inventory). (2026-11-20 19:58 ET)
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries; verified by reviewing the changed governance skill and lineage contract under [Answer](#answer). (2026-11-20 19:58 ET)
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred; verified by document review under [Traces](#traces), with no source operation run. (2026-11-20 19:58 ET)
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. PR #1988 squash-merged at 2026-11-21 07:02 ET as `7062c67867cc0a46edc72895b22cb1b56eefeeb0`; updated-head CI passed all 12 checks. (2026-11-21 07:17 ET)
- [x] Learning → skill: missing coverage or evidence must be named and unsupported lineage left unclaimed; recorded in [Shared rules](../../../skills/data-governance/SKILL.md#shared-rules), [Completion](../../../skills/data-governance/SKILL.md#completion) and [Coverage and evidence gaps](../../../skills/data-governance/LINEAGE.md#coverage-and-evidence-gaps). (2026-11-20 19:58 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Inventory

| Local instruction or gap | Authoritative source | Finding | Disposition |
|---|---|---|---|
| Approval, rule activation and switch-on boundaries | `CLAUDE.md`, "Talking with the operator"; `CONTEXT.md`, "Rule Activation Approval"; ticket 02 disposition | The governance skill describes evidence and publication; it grants no approval or activation authority. | State that the lineage contract grants no permission and point to Data Platform for activation rules. |
| Provider access and secrets | `CLAUDE.md`, "Commits, PRs and secrets"; Data Platform hard stops | These are shared operational rules, not lineage decisions. | Point to Data Platform; do not repeat credential handling or request provider access. |
| Configuration-only work and public data | Data Onboarding hard stops; `CLAUDE.md`, "Code and stores" | Governance consumes configured contracts; it does not own source configuration, and the public-repository value restriction applies. | Point to Data Onboarding and make no configuration or data-value exception. |
| Local proof and run evidence | `CLAUDE.md`, "Tests" and "Stay close to reality"; Data Operations | A proposed contract is not proof of processing; actual completion requires run evidence. | Point to Data Operations and distinguish configured intent from observed completion. |
| Test-scenario approval | Ticket scope and `CLAUDE.md`, "Tests" | No authority to create or run a scenario is granted by this documentation task. | Explicitly limit scenario creation and execution to a task that authorizes that exact scenario. |
| Completion/readback wording | Ticket 61; destination skill; `LINEAGE.md` | A successful write does not prove stored edges; configured coverage does not prove observed completion. | Name coverage and evidence gaps, leave unsupported edges unclaimed, and use destination native readback for stored edges. |
| Inputs and outputs | Ticket 02's shared disposition; ticket 61's ownership decision | The skill listed inputs and a neutral lineage contract but did not require explicit coverage/evidence gaps. | Describe inputs as configured contracts/reads, checks, control dependencies and run evidence; output a governed contract plus named gaps. |

## Traces

These are document traces, not execution evidence.

- **Routine:** a configured target has source contracts, declared checks and run evidence. Governance describes the supported source/control/step/output path, states the covered target, and cites observed completion only where run evidence supports it. Destination publication and native readback remain with the destination skill. No provider request, configuration edit, test scenario, approval or switch-on follows from this path.
- **Blocked:** a source contract, declared check, run record or destination readback is missing. Governance names the uncovered scope and evidence gap, leaves the unsupported edge or completion claim unclaimed, and hands execution/recovery to Data Operations or publication/readback to the selected destination skill. It does not request provider information or infer authority to activate a rule.

## Answer

The governance skill now reports its covered configured scope and names
coverage or evidence gaps; unsupported edges and unobserved completion remain
unclaimed. The lineage contract says which evidence establishes configured
intent, observed completion and destination state.

The shared rules section points approval/activation, provider access and
credentials to Data Platform; configuration and public-data handling to Data
Onboarding; and local proof/run evidence to Data Operations. It states that
this contract does not grant those permissions and that a test scenario must
be explicitly authorized by the task. Completion now identifies unavailable
run or readback evidence as a gap.

**Provenance.** `HEAD` and the checked-in `origin/main` ref are
`d650395c6d00b9adcf76d3afe890541afb280f14`. `git merge-base --is-ancestor`
returned 0 for ticket 02's `e166fa56`, ticket 14's `adee4305`, and ticket
61's `fcd075b6`. The cited prerequisite changes are present on this baseline;
their ticket files were not changed. `git fetch origin main` could not update
`FETCH_HEAD` because the shared Git metadata is outside the writable area.
The review's merge references also match the commits on this baseline:
`d650395c` (#1984), `51859666` (#1981) and `fcd075b6` (#1982). Tickets 25,
37 and 61 still say `Status: open`; their files were not changed.
The installed Data Governance path is a symlink to another checkout whose
target does not exist here, so that installed copy could not be compared. The
installed `write-skill` guidance was read; its edit ladder favors revising the
existing instruction, placing a fact at the lowest useful level, and checking
size and genericity. The repository skill is the copy changed.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py`: **142 passed**. This repository genericity check constrains documentation wording; it does not test lineage behavior.
- `git diff --check`: passed.
- Confirmed the new links resolve to the named skill headings. `skills/data-governance/SKILL.md` is 57 lines, below the 500-line limit.
- No other tests, provider requests, configuration changes, processing runs, scenario executions or destination readbacks were performed.
