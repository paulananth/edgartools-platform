# mdm-engineering: Reconcile shared rules

Type: task
Status: open
Priority: P2
Blocked by: 02, 14, 37
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [mdm-engineering](../../../skills/mdm-engineering/SKILL.md)
Step: 2 of 6
Skill dependencies: data-modeling
Applicability: Conditional: choose mastering proof or investigate a demonstrated engine or storage gap; configuration remains the default.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: the smallest sufficient proof, or a separately scoped capability-gap ticket with a failing behavior example.

Start from skills/mdm-engineering/SKILL.md: Hard stops, Choose the cheapest proof, Independent installed qualification. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [data-modeling: Reconcile shared rules](./14-data-modeling-consistent-rules.md); [mdm-engineering: Define one responsibility](./37-mdm-engineering-responsibility.md)

Priority rationale: Conditional mastering proof or demonstrated engine gap.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition; verified by comparing this skill's hard stops, proof guidance and handoffs with `CLAUDE.md`, Data Platform, Data Onboarding, Data Modeling and the onboarding map. Recorded under [Inventory](#inventory). (2026-11-20 19:57 ET)
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries; verified by reviewing the updated shared-rules pointer and proof wording in [MDM Engineering](../../../skills/mdm-engineering/SKILL.md#hard-stops) against the inventory. (2026-11-20 19:57 ET)
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred; verified by reading both paths against the current skill ownership and the rules cited below. No operation or scenario was run. (2026-11-20 19:57 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: shared operating rules belong to their authoritative owners; this skill points to them and keeps only MDM-specific proof guidance. Recorded in [Hard stops](../../../skills/mdm-engineering/SKILL.md#hard-stops). (2026-11-20 19:57 ET)

## Inventory

| Local instruction or omission | Authoritative source | Finding | Disposition |
|---|---|---|---|
| The proof section says delivery totals remain unchecked "until switch-on" and couples a whole-delivery proof to totals or switch-on | `CLAUDE.md`, "Long steps and runs" and "Stay close to reality"; Data Platform, "The seven wastes" | A total-count claim is distinct from switch-on; wording could imply switch-on is required to verify totals | State that full delivery is needed only for a delivery-total claim, and report totals unchecked when they were not measured. Switch-on remains separately gated. |
| MDM's local hard stops do not locate provider, credential, configuration-only, scenario-authorization or checklist rules | `CLAUDE.md`, "Commits, PRs and secrets", "Task checklists", and "Talking with the operator"; Data Platform hard stops; Data Onboarding hard stops; onboarding map execution note | Duplicating those cross-phase rules here would create competing copies; MDM currently needs a clear route to their owner | Add one pointer to the authoritative sections. This skill grants no permission; keep only MDM-specific qualification guidance locally. |
| Approved models, matching rules and steward decisions are named as inputs to or limits on MDM work | Data Modeling ownership and the matching-rule boundaries in MDM Engineering/Cross-reference completion; tickets 02 and 14 | Consistent with the current owner boundaries. The ordinary approval wording conflict remains open in the prerequisite decisions; no new approval is inferred here | Retain these qualified references and route shared approval/activation rules to their source. Do not resolve the open decision or claim operator approval. |
| Local engine and storage behavior checks, migration proof, installed qualification and proof sizing | MDM Engineering's ownership and `CLAUDE.md`, "Choose the cheapest proof" | MDM-specific detail with an appropriate owner | Keep the domain-specific method here; link only to the shared operating rules. |

Installed-skill provenance: `~/.agents/skills/mdm-engineering` and
`~/.claude/skills/mdm-engineering` resolve to a different checkout and differ
from this repository's copy. The current `origin/main` copy is the baseline.
`origin/main` contains the claimed prerequisite commits for tickets 25, 37
and 61; `git merge-base --is-ancestor` succeeded for `d650395c`,
`51859666` and `fcd075b6`, respectively. Their ticket files were not edited.
`gstack-skill-bill` reports no `Skill-Diet` baseline; the repository file was
38150 bytes before this change. The installed `write-skill` guidance was read;
its edit ladder supports revising existing proof wording and placing shared
rules at their owning level.

## Traces

These are instruction-path reviews, not executions.

- **Routine path:** a configured policy/contract expresses the requested merge behavior. Data Onboarding or Refining Rules owns its configuration. If a demonstrable reusable engine/storage gap remains, MDM Engineering receives that configuration and gap, selects the smallest sufficient proof and returns behavior and qualification evidence. The shared-rules pointer adds no provider request, approval or switch-on.
- **Blocked path:** an engine or storage operation is refused or lacks a reusable implementation. MDM Engineering records the unsupported behavior and demonstrated gap; no provider is contacted and no scenario/test code is added by this ticket. Any provider request, scenario authorization, approval or switch-on remains governed by the cited owner and is not granted by the skill.

## Answer

The skill now points shared operational rules to their owners and states MDM's own boundary: configuration remains the default, while this skill owns reusable engine/storage changes and their cheapest sufficient proof. It also separates verifying delivery totals from switch-on. The approval wording conflict carried by prerequisite tickets 02 and 14 remains unresolved; this change does not decide it. The installed skill remains a distinct copy in another checkout and was not modified.

## Validation

`uv run --no-project --with pytest -- pytest -q -p no:cacheprovider --rootdir . tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py` — **150 passed**. These checks cover skill size, genericity and named-path validity; they do not validate approval, provider access, switch-on or MDM behavior.

`git diff --check` — clean. `skills/mdm-engineering/SKILL.md` — 496 lines
(under the 500-line limit). `gstack-skill-bill` measured the file at 38150
bytes before and 38710 after; no `Skill-Diet` baseline exists.

## Completion evidence

The publication checklist item remains open because the user prohibited commit,
push and PR creation. This ticket is incomplete until publication and its
required checks are completed.

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
