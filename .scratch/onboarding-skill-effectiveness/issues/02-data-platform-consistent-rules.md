# data-platform: Reconcile shared rules

Type: task
Status: open
Priority: P0
Blocked by: 01
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 2 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: one selected next action, its owner and the required environment checks.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md)

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition; verified by document review of `CLAUDE.md`, `CONTEXT.md`, the data-platform, data-onboarding, refining-rules and data-onboarding `LOAD.md` texts, recorded under [Inventory](#inventory). ({{now}})
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries; verified by document review of the diff to `skills/data-platform/SKILL.md`, `CONNECTIONS.md` and `LOCAL-TESTING.md` against the inventory. ({{now}})
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred; verified by document review under [Traces](#traces). No source operation was run. ({{now}})
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. Checks ran (see [Validation](#validation)); not yet committed, pushed or opened as a PR.
- [ ] Open decisions recorded below are answered by the operator or carried by tickets 08 and 20.
- [ ] Learning → skill: proposed lesson in [Data Platform hard stops](../../../skills/data-platform/SKILL.md#hard-stops): a skill's rule list names each rule's home and grants no permission. Not ticked until the change is published and reviewed.

## Inventory

Authority order: explicit operator instruction, then `CLAUDE.md`, then
`CONTEXT.md` definitions, then the owning skill.

| # | Local instruction (data-platform) | Authoritative source | Finding | Disposition |
|---|---|---|---|---|
| 1 | Hard stops "In short" list claimed to summarize the data-onboarding hard stops | data-onboarding `## Hard stops` | Conflict: it listed three approval rules that table does not hold (approve/switch on, test run, digest) and left out two rows it does (configuration only; master data not in silver) | Replaced with a list that names each rule's home; the rows that live in data-onboarding stay there, behind a link |
| 2 | "Never approve or switch on for the operator" | `CONTEXT.md` "Rule Activation Approval"; `CLAUDE.md` "Talking with the operator" (stop for a switch-on) | Keeps the operator's boundary; "never approve" was broader than `CLAUDE.md`'s rule for routine steps | Data Platform approves nothing; activation and switch-on stay the operator's, given only when asked. The routine-approval wording across skills is open decision A |
| 3 | "Never approve without a test run" | `CONTEXT.md` "Proving Run"; refining-rules hard stop (no switch-on without measured proof) | Duplicate | Kept as part of the activation line, cited to its home |
| 4 | "Never ask approval of a digest the operator cannot read" | `CLAUDE.md` "Talking with the operator" (a digest goes beside the explanation) | Duplicate | Cited to `CLAUDE.md` |
| 5 | "No request to a provider the operator ruled out"; Source readiness "Provider requests retain their separate authorization" | `CLAUDE.md` "Commits, PRs and secrets": no request without permission for that request | Conflict: "ruled out" allows any provider not listed | Restated as permission per request, cited to `CLAUDE.md`; Source readiness points to Hard stops |
| 6 | "Never read or print a secret" | `CLAUDE.md`: read secrets from environment variables, never print, operator sets a missing one; `CONNECTIONS.md` | Conflict: "never read" contradicts reading from configuration | Read from configuration, never print; pointer to Connection URLs and environment |
| 7 | Connection section: the loader login and "no agent opens the stores folder" | `CONNECTIONS.md`, the sole owner of connection instructions (its duty table already holds the loader row) | Duplicate outside the owner | Moved into `CONNECTIONS.md`; SKILL.md keeps a pointer |
| 8 | Mode 6 custom parsing began "write one plain function" with no gate | data-onboarding hard stop "configuration only: write the ticket, ask before coding"; operator memory "Configuration only" | Conflict inside data-platform | Mode 6 starts only after the operator says to write the step; while onboarding, write the ticket and ask first |
| 9 | Master: "this slice does not change approval or activation steps" | `CLAUDE.md` "Say what is, never what was" | Change-history wording about approval | Removed the clause; the parity requirement stays |
| 10 | "Examples: current source qualification" claimed installed proofs that carry forward | data-platform's own handoff row (Data Platform does not certify readiness); `CLAUDE.md` "Stay close to reality" | Conflict: completion claim with no measurement or location | Removed; the `workers describe` check stays in Parse |
| 11 | `LOCAL-TESTING.md` "Each agent gets its own writable copy" | `CLAUDE.md` "Shared local data" (the shared server replaces the per-agent copy) | Conflict on where local proof runs | Routine work uses the shared `local-test-server`; a copy is only for a test that could disrupt shared data |
| 12 | `LOCAL-TESTING.md` "no intermediate approval prompts" | `CLAUDE.md` "Do not ask for approval" | Consistent | No change |
| 13 | Seven wastes "Waiting: decide what follows from a ruling"; "ask one question at a time" | `CLAUDE.md` "Talking with the operator" | Duplicate, consistent | Kept the waste row; the question rule is a data-onboarding hard stop behind a link |
| 14 | Source readiness: fixture tests are implementation evidence, not readiness | `CLAUDE.md` "Stay close to reality"; "A conclusion reached by reading code is not proof" | Consistent; it is the local phase rule | No change |
| 15 | Test-scenario approval | The map's execution note: proposed Given–When–Then scenarios need the operator's approval | data-platform holds no scenario rule; nothing to reconcile | No change; no scenario or test code added |
| 16 | Completion wording | `CLAUDE.md` "Task checklists" (unchecked part means "incomplete"); data-onboarding narration labels a result as explored, checked or loaded | Consistent; data-platform's "a phase is complete only under its owning skill's evidence" | No change |

Findings outside this skill's files (for tickets 08 and 20, not edited here):
the data-onboarding hard stops keep "a provider the operator has ruled out"
(row 5's conflict) and "read, print or paste a secret" (row 6's conflict).

## Open decisions

- **A. Routine approvals.** `CLAUDE.md` says do not ask for approval and
  record a step's approval as given, stopping only for a switch-on or a new
  kind of decision. Data-onboarding (findings approval "are the operator's,
  one at a time") and `profile_data.py approve` ("the operator's approval, in
  their exact words") ask for the operator's own words. Data Platform does not
  settle which wins for findings and contracts; it approves nothing. Needs the
  operator's ruling, or tickets 08 and 20.

## Traces

Document traces of the routing output in
[Decisions, artifacts and handoffs](../../../skills/data-platform/SKILL.md#decisions-artifacts-and-handoffs).
These are readings of the text, not source runs.

- **Routine path:** a configured source receives a new delivery. Next action:
  a repeat load. Owner: Data Operations, with the source runbook and latest
  Bookkeeping/Journal status. Environment checks: the loader duty's variable
  names from `CONNECTIONS.md` and `edgar-warehouse doctor`. No approval,
  provider request or switch-on is part of that route. Reading retained files
  is not a provider request.
- **Blocked path:** a new source whose field definitions only the provider's
  documentation holds. The route is Data Onboarding's discover step. Reading
  that documentation needs the operator's permission for that request (Hard
  stops). So the next action is to name that blocker to the operator and
  stop. If the source also needs a custom step, Mode 6 stops until the
  operator says to write it. Neither the route nor the stop grants permission
  or approval.

## Answer

Data Platform's rule list now names each rule's authoritative home and grants
no permission. The conflicts it held (provider access default-allow, "never
read a secret", an ungated code step, a per-agent local copy, an uncited
readiness claim) are aligned to `CLAUDE.md` and `CONTEXT.md`. Activation and
switch-on remain the operator's. The routing output is one next action, its
owner and its environment checks. Open decision A remains for the operator.

Provenance: the checkout is `f8233ff2` on
`claude/ticket-02-data-platform-consistent-rules-20261120`, which contains
ticket 01 (PR #1956). That was checked with `git merge-base --is-ancestor`
against `origin/main`. `~/.agents/skills/data-platform` is a dangling symlink
to `~/.local/share/edgartools/skill-source/skills/data-platform`, so no
installed data-platform copy was available to compare. The requested
`~/.agents/skills/write-skill/SKILL.md` was read; it is generated from the
gstack `write-skill` template, per its header, and recommends editing existing
guidance, keeping each fact at the lowest useful level and checking genericity
and size. The repository data-platform skill is the copy changed.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py`: **149 passed**. These check skill wording (no ticket numbers or dates, line limit, genericity) and the paths `CLAUDE.md`/`AGENTS.md` name. They do not exercise routing behaviour.
- `git diff --check`: clean.
- `tests/unit/test_skill_bundle_portability.py` did not run: it imports `edgar_warehouse`, and this worktree has no synced environment. The new links (`#hard-stops`, `#connection-urls-and-environment`, `CONNECTIONS.md`, `SKILL.md#0-setup`, `../data-onboarding/SKILL.md#hard-stops`) were checked by hand against the headings.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
