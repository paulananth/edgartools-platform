# data-modeling: Reconcile shared rules

Type: task
Status: open
Priority: P0
Blocked by: 02, 08, 13
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 2 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: a model decision per part with identity versus lookup choices and destination rationale.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [data-profiling: Reconcile shared rules](./08-data-profiling-consistent-rules.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition; verified by document review of `CLAUDE.md`, `CONTEXT.md`, the data-platform, data-onboarding and data-profiling hard stops, `CODE-SETS.md`, the map's execution note and the data-modeling `SKILL.md` and `REQUIREMENTS.md`; recorded under [Inventory](#inventory). (2026-11-20 19:11 ET)
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries; verified against the current-main skill and the operator ruling recorded under [Open decisions](#open-decisions). Findings and designed keys remain explicitly approved; each new relationship-type/capacity code-set version needs the operator's exact words before publication. No approval, provider access or switch-on authority is inferred. (2026-11-21 21:07 ET)
- [x] Reconcile "one of `KINDS`" with `mdm-kinds` as the one list of kinds (deferred here by [13](./13-data-modeling-responsibility.md)); verified by code reading: `rules/mastering/engine-v1.yaml` pins `mdm-kinds` version 1, and `edgar_warehouse/mdm/catalog.py` `_read` fills `kinds` from that published code set, which `evidence.py` reads as `KINDS`. Section 2 and REQUIREMENTS name `mdm-kinds`. No behaviour test was run. (2026-11-20 19:11 ET)
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred; verified by document review under [Traces](#traces). No source operation, proof program, RDM operation or load was run. (2026-11-21 21:07 ET)
- [x] Open decision A (routine approvals, carried from tickets 02 and 08) is resolved by the operator: findings and designed keys retain explicit approval (ticket 08); each new relationship-type/capacity code-set version requires exact operator words before publication, and standing routine approval is insufficient. Recorded under [Open decisions](#open-decisions). (2026-11-21 21:07 ET)
- [x] Learning → skill: exact operator words are required before publishing every new relationship-type/capacity code-set version; standing routine approval is insufficient. Recorded in [Data Modeling hard stops](../../../skills/data-modeling/SKILL.md#hard-stops). (2026-11-21 21:07 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. Draft until current-head CI is green.
- [x] Open decision A (routine approvals, carried from tickets 02 and 08) is resolved by the operator: findings and designed keys retain explicit approval (ticket 08); each new relationship-type/capacity code-set version requires exact operator words before publication, and standing routine approval is insufficient. Recorded under [Open decisions](#open-decisions).
- [x] Learning → skill: exact operator words are required before publishing every new relationship-type/capacity code-set version; standing routine approval is insufficient. Recorded in [Data Modeling hard stops](../../../skills/data-modeling/SKILL.md#hard-stops).

## Inventory

Authority order (ticket 02): explicit operator instruction, then `CLAUDE.md`,
then `CONTEXT.md` definitions, then the owning skill. Ticket 02's disposition:
a rule list names each shared rule's home and grants no permission.

| # | Local instruction (data-modeling) | Authoritative source | Finding | Disposition |
|---|---|---|---|---|
| 1 | Hard stops had no statement of what the list is | Tickets 02 and 08 disposition | Gap | Added the line data-profiling uses: a shared rule names its home; the list grants no permission |
| 2 | Hard stop "Approve findings or a code set version, or write words the operator did not say" | data-profiling hard stops (`approve`); `CODE-SETS.md` step 4; `CONTEXT.md` "Rule Activation Approval"; `CLAUDE.md` "Do not ask for approval"; ticket 08's operator ruling | The shared-rule conflict is settled: findings and designed keys retain explicit approval; each relationship-type/capacity code-set version requires exact operator words before publication | The row names the approval owners and records the specific version gate; standing routine approval is insufficient, and switching a rule on remains the operator's |
| 3 | Hard stop and refusal "Request anything from a provider's live service" | `CLAUDE.md` "Commits, PRs and secrets" (site, API or documentation, permission per request); data-platform hard stops | Conflict: "live service" left documentation uncovered | Widened to site, API or documentation, with permission per request. The permission path differs from data-profiling's row (which has none) because row 4's provider-published standard needs it; the "Instead" column still names the blocker to the operator and stops, and never self-requests |
| 4 | Hard stop "Propose a domain rule … First find how a public standard or the main vendors do it" | `CLAUDE.md` provider rule | Conflict: read as leave to fetch a standard the data's own provider publishes | Added: a standard published by the data's own provider is a provider request and needs permission for that request |
| 5 | Examples "*Proving it.*" named a real company | `CLAUDE.md` "This repository is public: counts and invented examples only"; data-onboarding hard stops | Conflict | Replaced by its shape ("a large US common stock"). New hard stop and refusal: no data value in a public repository (a committed decision, proof report or example). The rule covers the public record only; a real public record shown in chat when the operator asks for an example is unaffected. Place codes, namespace names and relationship-type names are vocabulary, not records: consistent |
| 6 | Section 9 "Report per case" gave counts without where they were measured | `CLAUDE.md` "Stay close to reality" (every number with where it was measured; an estimate says so); data-profiling narration ("measured" against "not yet tested") | Gap in completion wording | Each case named by shape, each count with its captures, what was not run marked not yet tested |
| 7 | Section 9 "Run the decided rules in memory … a short program outside the repository" | `CLAUDE.md` "Stay close to reality" (a real capture on a disposable store); mdm-engineering "Choose the cheapest proof"; the map's execution note (scenarios need approval before implementation) | Partial conflict: the in-memory run could read as the change's proof | Stated as a model proof before any build; a built change is proved by MDM Engineering on a real capture. The program stays outside the repository, as the step already says. No approval gate was added: the map's scenario note governs this ticket series, not the skill, and code while onboarding is already gated by the data-onboarding hard stops |
| 8 | "What the platform already says": how to write a published file (`rdm.store.canonical`, `pin.json`, the CI test) | `CODE-SETS.md` step 5 (Publish); data-onboarding `REFERENCE.md` (never by hand); this skill's own hard stop (writes no code set version) | Duplicate of the owner's step, and in conflict with the hard stop | Replaced by a pointer to `CODE-SETS.md` step 5; the rule that types live in RDM stays |
| 9 | Section 2 and REQUIREMENTS "one of `KINDS`" (deferred by ticket 13) | data-profiling "Identify an MDM kind" (`mdm-kinds`, "Nothing else holds a list of kinds"); the operator's rule this skill quotes, "types and reference data must not be in files" | Inconsistent naming, not a second list: `KINDS` is the engine's read of the pinned `mdm-kinds` version (`engine-v1.yaml`, `catalog.py`) | Both name `mdm-kinds` as the list; `KINDS` is described as the engine's read |
| 10 | Hard stop "Ask one question, then wait"; Workflow step 6 "Ask at most one question … Give the recommendation" | `CLAUDE.md` "Talking with the operator"; data-onboarding hard stops | Duplicate, consistent | New hard stop row cites data-onboarding; step 6 unchanged |
| 11 | Hard stop "Add a kind"; step 6's operator questions (new kind, identity namespace, second type, which field is identity) | `CLAUDE.md` "Stop only for a switch-on or a new kind of decision" | Consistent | No change |
| 12 | Hard stop "Join records … only through … a matching rule the operator switched on"; exposure "Consumer activation and billable mirror creation retain their own gates" | `CONTEXT.md` "Rule Activation Approval"; data-platform `FINAL-TABLES.md` | Consistent: no activation authority | No change |
| 13 | Exposure "do not add another tagging approval round" | `CLAUDE.md` "Do not ask for approval" | Consistent | No change |
| 14 | Configuration only: "does not … write configuration"; hard stop "Write rules, contracts, quality files, or a code set version" | data-onboarding hard stop "Configuration only" | Consistent: this skill writes no configuration or code | No change |
| 15 | Secrets | `CLAUDE.md` secrets rule; data-platform hard stops | data-modeling handles no credential | No change |
| 16 | REQUIREMENTS "First written by Grok; handed to Claude…" and heading "Settled since the first version"; Examples "OpenFIGI had been loaded as … replaced them" | `CLAUDE.md` "Say what is, never what was" | Conflict: history wording | Removed the provenance sentence; heading is "Built"; the example states the current one-target load |
| 17 | Section 5 "approved in the operator's words, published, and pinned" | `CODE-SETS.md` step 4; ticket 08's approval ruling; the operator's ruling recorded below | Resolved: findings/design keys remain explicitly approved; every new relationship-type/capacity code-set version requires exact operator words before publication | The wording in section 5 aligns with the RDM approval gate; no standing routine approval can authorize publication |

Findings outside this ticket's topics, not edited here:

- Section 3 "Today" says the one Cross-reference table "is decided and not
  built"; the Examples say "The one table is built for Security first". Which
  is current was not settled by a quick reading of `edgar_warehouse/mdm`; it
  needs a code check under a model-review ticket.
- REQUIREMENTS open question 2 (overlapping parent types, unnoted inverse fund
  types) may be partly answered by the Examples' "Real names" ruling on
  GLEIF's two names. Not changed without the operator's confirmation.

## Open decisions

- **A. Routine approvals (from tickets 02 and 08), this skill's part — resolved by the operator.** Ticket 08's ruling keeps explicit approval for findings and designed keys; its private, sanitized review view is only a review aid, not consent (`approve --words` remains the approval record). The operator's ruling for this skill is: "each new relationship-type/capacity code-set version requires exact operator words before publication; standing routine approval is insufficient." Therefore, the exact words must be recorded for each version before publication; the skill grants no standing approval. The finding/design-key approvals remain required and do not substitute for approval of a code-set version.

## Traces

These are readings of the current text, not runs.

- **Routine path:** Data Onboarding hands over findings whose `approval.status`
  is `approved`, including explicit operator approval of the findings and any
  designed key (ticket 08). The part uses an existing kind, declared
  identifiers and an already published relationship type/capacity. Data
  Modeling decides the class, kind, identity versus lookup-only identifiers
  and time columns, then hands off the decision. No new code-set publication,
  provider request or switch-on occurs; routine use of an existing version
  does not stand in for explicit findings or designed-key approval.
- **Blocked path:** a part needs a new relationship type or capacity not held
  in the pinned RDM version. Data Modeling names the gap and hands the proposal
  to the code-set owner; it does not draft, approve or publish. The owner must
  show the exact draft and diff and record the operator's exact words for that
  version before publication. A standing routine approval is insufficient.
  If the proposal depends on documentation only the provider holds, that
  request separately needs the operator's permission; name the blocker and
  stop. Neither path grants provider access or switch-on authority.

## Answer

Data Modeling's hard stops name each shared rule's home and grant no
permission. The current-main skill:

- covers a provider's site, API and documentation, with permission per
  request, including a standard the data's own provider publishes;
- keeps data values out of the public repository (a committed decision,
  proof report or example), and its one real company name is replaced by a
  shape;
- states that the in-memory proof checks the model, not a built change, and
  gives each count with where it was measured;
- points to `CODE-SETS.md` for publishing instead of restating the step;
- names `mdm-kinds` as the one list of kinds;
- drops history wording from REQUIREMENTS and the Examples;
- requires explicit operator approval of findings and designed keys, and
  exact operator words for each new relationship-type/capacity code-set
  version before publication.

Decision A is resolved by the operator as quoted under [Open decisions](#open-decisions). No RDM version was drafted, approved or published.

Provenance:

- **Baseline.** `origin/main` at `5b2c90735` (PR #2007); this branch was
  created from that current-main head after fetching `origin/main`.
- **Prerequisites.** Tickets 02, 08 and 13 are resolved on current main:
  `e166fa56` (PR #1966), `d2879db5` (PR #1972) and `5b2c90735` (PR #2007).
- **Installed copy.** `gstack-skill-bill` found no installed `data-modeling`
  skill in its configured skill roots. The repository copy is the edit source.
- **Skill-writing guidance.** `write-skill` was read; the repo skill bill
  measured the current file before and after the edit (see Validation).

## Validation

- The `data-modeling` skill was reviewed against current main, ticket 08's explicit findings/design-key approval ruling, and the operator's exact relationship-type/capacity version ruling. The repository copy was changed; no RDM version was drafted, approved or published.
- `gstack-skill-bill` on the repository skill: **35,344 → 35,513 bytes**; `SKILL.md` is **491 lines**, within the 500-line limit.
- No local tests or provider/data operations were run, per assignment; the parent will run the combined focused checks. Current-head CI is still required before this draft PR can be marked ready.
- `bash scripts/dev/overlap_guard.sh` passed standalone: no overlap (2 files checked against other runtimes).

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
