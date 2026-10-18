# Guide data-platform work from current state to completion

Status: skill guidance implemented and locally validated; review PR
[#1077](https://github.com/paulananth/edgartools-platform/pull/1077) is open. CI
results are tracked on the PR; no merge was requested or performed. The operator asked the skill to explain the current
state and provide step-by-step guidance through completion, rather than
returning a generic missing-proof or missing-integration answer.

Scope: source-neutral data-platform instructions, a focused completion
reference, explicit MDM cross-reference ownership and matching agent metadata. Current deployment facts remain in
operational records, not hardcoded into shared skill behavior. Source
activation and runtime engineering are not performed by this documentation
change.

## Checklist

- [x] Inspect main `059d1758`, dedicated branch/worktree, writing-for-agents/skill-creator guidance and supported Rules lifecycle; existing native cross-reference migration, model definitions and history reviewed — 2026-10-18 12:43 ET.
- [x] Add a mandatory completion route, live per-target state explanation and completion-guide entry in the flow table; reference/anchor checks pass — 2026-10-18 12:43 ET.
- [x] Document nine ordered steps with observable completion criteria: state, native integration, inputs, MDM cross-references, qualification, proof recording, approval, activation and verified operation — 2026-10-18 12:43 ET.
- [x] Align trigger description and UI prompt; preserve discovery policy and dependencies, validate metadata length and skill invocation token — 2026-10-18 12:43 ET.
- [x] Walk through the eight decision scenarios below; explicitly distinguish manual guidance review from executed runtime qualification — 2026-10-18 12:43 ET.
- [x] Validate both skills, 25 affected genericity/mapping tests (0.71 seconds), 36 local links/anchors, five actual lifecycle help commands and four exact packaged resources — 2026-10-18 12:43 ET.
- [x] Review Standards, Spec and GoF against final documentation; no runtime/schema refactor or pattern hierarchy added — 2026-10-18 12:43 ET.
- [x] Commit `e8000791`, push the dedicated branch and open review PR [#1077](https://github.com/paulananth/edgartools-platform/pull/1077); CI is pending and its live results remain on the PR checks — 2026-10-18 12:45 ET.
- [x] Learning → skill: data-platform now follows COMPLETION.md through missing evidence and authorized engineering to verified operation; mdm-engineering owns cross-reference completion and its native per-engine proof — 2026-10-18 12:43 ET.


## Manual scenario walkthrough

These are decisions checked against the instructions and existing runtime,
not claims that a live source was activated by this change.

| Given state | Required path checked |
|---|---|
| Draft without proof, captures retained | Discover inputs, run the owning test mode, generate a measured proof and record it; no requirement for the operator to supply an existing final release. |
| Captures unavailable | Search known operational/artifact references, name the missing artifact, ask only for the unresolved input and continue independent work. |
| Local mapping passes, acquisition incomplete | Retain local qualification separately; a source declaring acquisition cannot record a passing source proof without its required evidence. |
| Storage fixture passes, native backend refuses | Carry the authorized engineering task through its owner and per-engine qualification; preserve incomplete status and continue other targets. |
| Exact tested release already approved | Reuse matching evidence and applicable existing authorization; promote the same content without an unnecessary new test/permission loop. |
| Recorded proof fails | Retain failing status, repair/rerun and follow the shared permitted-overrule procedure; missing test evidence is not an overrule. |
| Active version, delivery unprocessed | Continue/resume native workers, independent verification and Journal/publication receipts; verify the unchanged repeat. |
| Lookup value shared by multiple records; some unbound or merged | MDM lookup retains multiplicity and unbound results, follows authorized canonical redirects and preserves provenance. RDM code crosswalks and identity-binding rules remain distinct. |

## Standards

Shared guidance is source/domain neutral. Current operational values remain in
operational records. Existing approval and provider authorization semantics are
preserved; guidance tells the agent to complete concrete preparation and reuse
existing authorization before asking for a missing decision. Changes are four
skill resources and this task record, with no application/schema changes.
Both skill validators, selected testmon checks, link/anchor checks, current CLI
help and packaged byte equality pass. Other runtimes' WIP is preserved and the
overlap guard passes.

## Spec

The operator asked for current-state explanation and step-by-step skill guidance
through completion, then identified cross-references as an omitted MDM concern.
Data-platform now explains each target and carries work through nine explicit
stages. MDM engineering owns the cross-reference storage/lookup/provenance
contract and its per-engine qualification; the guide delegates to that contract.
The repository already implements native PostgreSQL cross-references as a view
and indexed lookup over retained MDM readings. This update documents and routes
that capability; it creates no duplicate table or new write path.

The update does not itself implement missing native engine backends, generate
source-specific release proofs or activate a source. It requires future invoked
agents to perform that work within the authorized scope and retain explicit
remaining prerequisites rather than declaring storage fixtures operational.

## GoF

`gof-refactor-reviewer` is available and its evidence/cost method was applied to
the ownership/routing review. History reviewed includes the selected-engine
skill change and the native cross-reference migration. The current Adapter
boundary and MDM-derived lookup preserve one authority; a separate registry or
new pattern hierarchy would add synchronization and review cost without solving
the missing native integration. Keep the design. This documentation diff adds
ordered guidance and explicit completion criteria, not a structural code change.
