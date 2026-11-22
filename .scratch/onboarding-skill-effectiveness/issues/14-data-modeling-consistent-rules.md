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
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries; verified against current-main `skills/data-modeling/SKILL.md` from merged PR #2007 (`5b2c9073`): each new relationship type or capacity is a code in a new `mdm-relationship-types` version and requires the operator's explicit words for that version before publication; standing routine approval is insufficient. The skill does not approve or publish it. (2026-11-21 21:17 ET)
- [x] Reconcile "one of `KINDS`" with `mdm-kinds` as the one list of kinds (deferred here by [13](./13-data-modeling-responsibility.md)); verified by code reading: `rules/mastering/engine-v1.yaml` pins `mdm-kinds` version 1, and `edgar_warehouse/mdm/catalog.py` `_read` fills `kinds` from that published code set, which `evidence.py` reads as `KINDS`. Section 2 and REQUIREMENTS name `mdm-kinds`. No behaviour test was run. (2026-11-20 19:11 ET)
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred; verified by document review under [Traces](#traces). No source operation, proof program or load was run. (2026-11-20 19:11 ET)
- [ ] Publish this ticket-record update in its own branch and PR; keep the PR draft until CI passes for the current head, then mark ready and merge via repo policy.
- [x] Open decision A (routine approvals, carried from tickets 02 and 08) is resolved by the operator: findings and designed keys retain explicit approval (ticket 08); each new relationship-type/capacity code-set version requires the operator's exact words for that version before publication, and standing routine approval is insufficient. No publication or switch-on is authorized. Recorded under [Open decisions](#open-decisions). (2026-11-21 21:17 ET)
- [x] Learning → skill: each new relationship-type/capacity code-set version requires exact operator words before publication; standing routine approval is insufficient. Already implemented in merged PR #2007 and verified in `skills/data-modeling/SKILL.md` lines 281–286; no duplicate skill edit. (2026-11-21 21:17 ET)

## Inventory

Authority order (ticket 02): explicit operator instruction, then `CLAUDE.md`,
then `CONTEXT.md` definitions, then the owning skill. Ticket 02's disposition:
a rule list names each shared rule's home and grants no permission.

| # | Local instruction (data-modeling) | Authoritative source | Finding | Disposition |
|---|---|---|---|---|
| 1 | Hard stops had no statement of what the list is | Tickets 02 and 08 disposition | Gap | Added the line data-profiling uses: a shared rule names its home; the list grants no permission |
| 2 | Hard stop "Approve findings or a code set version, or write words the operator did not say" | data-profiling hard stops (`approve`); `CODE-SETS.md` step 4; `CONTEXT.md` "Rule Activation Approval"; operator's D4 ruling | The per-version publication approval is explicit: each new relationship-type/capacity version needs exact words; routine approval is insufficient | Current-main skill says the type/capacity must be an RDM code in a new version and requires explicit operator words for that version before publication; it grants no publication or switch-on authority |
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
| 17 | Section 5 "approved in the operator's words, published, and pinned" | `CODE-SETS.md` step 4; operator's D4 ruling; `CONTEXT.md` "Rule Activation Approval" | The exact-version gate applies; routine approval alone is insufficient | Current-main skill requires explicit operator words for every new relationship-type/capacity version before publication; no approval or publication was performed here |

Findings outside this ticket's topics, not edited here:

- Section 3 "Today" says the one Cross-reference table "is decided and not
  built"; the Examples say "The one table is built for Security first". Which
  is current was not settled by a quick reading of `edgar_warehouse/mdm`; it
  needs a code check under a model-review ticket.
- REQUIREMENTS open question 2 (overlapping parent types, unnoted inverse fund
  types) may be partly answered by the Examples' "Real names" ruling on
  GLEIF's two names. Not changed without the operator's confirmation.

## Open decisions

- **A. Routine approvals (from tickets 02 and 08), this skill's part — resolved by the operator.** Findings and designed keys retain explicit approval. Each new relationship-type/capacity code-set version requires the operator's exact words for that version before publication; standing routine approval is insufficient. Those words must be recorded for that version. They do not authorize publication or switching a rule on.

## Traces

These are readings of the current text, not runs.

- **Routine path:** Data Onboarding hands over a part with approved findings
  that name an existing kind and identifiers its Identifier Contract already
  declares. Data Modeling reads the findings and `mdm-kinds`, decides the
  class, the kind, which identifiers match and which are lookup only, and the
  time columns, and writes the decision in counts and shapes. It does not
  change how records join, so section 9 is not required. It hands the
  decision to Data Onboarding, which writes the configuration. No approval,
  provider request or switch-on is part of this path.
- **Blocked path:** a part needs a new relationship type or capacity not held
  in the pinned RDM version. Data Modeling names the gap and hands it to the
  code-set owner; it does not draft, approve, publish or switch on the code.
  The owner must show the exact draft and diff and obtain the operator's
  exact words for that version before publication. Standing routine approval
  is insufficient. If the proposal depends on documentation only the provider
  holds, that request separately needs the operator's permission; name the
  blocker and stop. Neither path grants provider access.

## Answer

The current-main Data Modeling skill (merged PR #2007, `5b2c9073`) already
implements the D4 ruling. It says every relationship type and capacity is an
RDM code in a new `mdm-relationship-types` version; the operator must give
explicit words for that version before publication, and standing routine
approval does not authorize publication. It then pins the version before a
contract, rule or test names the code. This directly covers the exact version
gate, so the skill is not edited again.

No code-set version was drafted, approved or published, and no rule was
switched on. Ticket 14's shared-rule reconciliation is complete once this
ticket-record PR passes current-head CI and is merged.

## Provenance

- **Baseline.** Freshly fetched `origin/main` at `4b75afe3a`; merged PR #2007
  (`5b2c9073`) is an ancestor and contains the skill rule verified above.
- **Prerequisites.** Tickets 02, 08 and 13 are resolved on current main, as
  confirmed in the task context. Their changes are already part of `origin/main`.
- **Installed copy.** No `data-modeling` skill was found in the checked runtime
  locations `~/.agents/skills`, `~/.claude/skills` or `~/.codex/skills`.
  The repository copy is current and already contains the rule. No skill edit
  was made; a before/after skill bill is therefore not applicable.
- **Skill-writing guidance.** `gstack-skill-bill` is not available among the
  installed skills. No skill-writing operation was needed because PR #2007
  already implemented the ruling.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider --rootdir <worktree> tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py`: **149 passed**. These check skill wording (no ticket numbers or dates, the 500-line limit, genericity) and the paths the guides name. They do not exercise approval, provider access, privacy or routing behaviour.
- `git diff --check`: clean.
- The rewritten OpenFIGI example ("one target … whether the question was a CUSIP or an ISIN") was checked against `rules/sources/openfigi/source.yaml` `bookkeeping.targets` (one target over both kinds asked). A broader clause about source rules pairing the two was dropped: `rules/sources/sec.nport.security/source.yaml` reads a CUSIP–ISIN pair set.
- `skills/data-modeling/SKILL.md`: 477 lines. No heading was renamed; the REQUIREMENTS heading "Built" has no inbound link (grep of `skills`, `tests`, `docs`).
- New links (`../data-profiling/SKILL.md#hard-stops`, `../data-platform/SKILL.md#hard-stops`, `../data-onboarding/SKILL.md#hard-stops`, `../mdm-engineering/SKILL.md#choose-the-cheapest-proof`, `CODE-SETS.md` step 5) were checked by hand against those files' headings and steps.
- `tests/unit/test_role_skills.py` (names data-modeling) and `tests/unit/test_skill_bundle_portability.py` did not run: both import `edgar_warehouse`, and this worktree has no synced environment (`.venv/bin/pytest` is absent).
- `bash scripts/dev/overlap_guard.sh` was not run: nothing is committed, and the `2026-11-20 19:11 ET` stamps are filled only by `commit_push.sh`.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
