# access-audit: Reconcile shared rules

Type: task
Status: resolved
Priority: P1
Blocked by: 02, 79
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [access-audit](../../../skills/access-audit/SKILL.md)
Step: 2 of 6
Skill dependencies: data-platform
Applicability: Review the skill or access changes being finalized; run only applicable read-only platform checks.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: PASS, FAIL and NOT_TESTED evidence with a coverage matrix and separate remediation references.

Start from skills/access-audit/SKILL.md: Hard stops, Objectives, The gate before finalising a skill role or login. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [access-audit: Define one responsibility](./79-access-audit-responsibility.md)

Priority rationale: Independent access evidence is cross-cutting; remediation is separate.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition; verified by document review of `CLAUDE.md`, `CONTEXT.md`, the map's execution notes, ticket 02's inventory, `skills/access-audit/SKILL.md` and the sections of `aws-snowflake-operations`, `data-operations/HOSTED-LOADS.md` and `data-platform/CONNECTIONS.md` that it hands to, recorded under [Inventory](#inventory). (2026-11-20 18:37 ET)
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries; verified by document review of the diff to `skills/access-audit/SKILL.md` against the inventory, and by the wording, genericity and path checks under [Validation](#validation), which do not exercise audit behaviour. (2026-11-20 18:37 ET)
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred; verified by document review under [Traces](#traces). No audit, load or provider request was run. (2026-11-20 18:37 ET)
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. Ticket-evidence-only PR [#2011](https://github.com/paulananth/edgartools-platform/pull/2011) is published as a draft from `codex/ticket-80-access-audit-consistent-rules-20261121`; its first current-head CI run passed, and CI will rerun for this completion-record commit before the PR is readied.
- [x] Open decision A for access changes is explicitly deferred to ticket 92, as this ticket permits; it remains unresolved and no access-change approval wording is inferred.
- [x] Learning → skill: a risk acceptance closes a finding only in the operator's own words, and a change that touches no platform records the gate as not applicable, never PASS. Recorded in [Access audit hard stops](../../../skills/access-audit/SKILL.md#hard-stops) and [the gate](../../../skills/access-audit/SKILL.md#the-gate-before-finalising-a-skill-role-or-login); verified by document review of the diff. (2026-11-20 18:37 ET)

## Inventory

Authority order (ticket 02): explicit operator instruction, then `CLAUDE.md`,
then `CONTEXT.md` definitions, then the owning skill. `CONTEXT.md` defines no
access-audit term, so no row cites it.

| # | Local instruction (access-audit) | Authoritative source | Finding | Disposition |
|---|---|---|---|---|
| 1 | Hard stops held shared rules with no home named | Ticket 02's disposition (a rule list names each rule's home and grants no permission) | Duplicates without a citation | Lead line added: a shared rule keeps its home, named in its row, and the table grants no approval, provider access, access change or switch-on. Rows 2–4 below name their homes |
| 2 | Never use the operator's overall administrator account | `aws-snowflake-operations` "Access identities" (bullet 1) | Duplicate, consistent. The account name stays because `audit_platforms/snowflake.py` refuses it by that name | Kept as the local enforcement and cited to Access identities |
| 3 | Never print a password, key, token, address or a value from the data | `CLAUDE.md` "Commits, PRs and secrets" (never print a secret; the repository is public, counts only) | Duplicate, consistent | Cited to `CLAUDE.md` |
| 4 | Never mark a control PASS from reading code or a document | `CLAUDE.md` "Tests" (a conclusion reached by reading code is not proof of behaviour) | Duplicate, consistent; it is the local phase rule | Cited to `CLAUDE.md` |
| 5 | A finding closes on "a signed acceptance of the risk"; the gate accepts a "signed acceptance (owner, reason, expiry date)" | `CLAUDE.md` "Talking with the operator": record a step's approval as given, but stop for a switch-on or a new kind of decision | Conflict: "signed" had no meaning in a Markdown ticket, so the standing rule ("record it as given") could be read as letting an agent accept a security risk | New hard stop: a signed acceptance is the operator's own words, with the ET time, owner, reason and expiry, given when asked. Accepting a risk is a new kind of decision, never a routine approval. The gate points to that row |
| 6 | Run it: sourcing `reader.env` and the audit variables | `data-platform/CONNECTIONS.md`, the owner of login files and duties (ticket 02, row 7) | Partial duplicate: the variable names belong in the entrypoint, but the login's duty does not | Variable names kept; a pointer to `CONNECTIONS.md` added for the files and duties |
| 7 | Run it reaches Snowflake and AWS without naming their skill | `CLAUDE.md` "Skills and guides": open `aws-snowflake-operations` before any AWS or Snowflake command | Gap: the entrypoint did not route there | One-line pointer added |
| 8 | Provider access | `CLAUDE.md` "Commits, PRs and secrets": no request to a data provider without permission for that request | Consistent: the audit reads platforms' own access records (Snowflake, AWS, GitHub, PostgreSQL, the workstation). It sends no request to a data provider | One sentence added to Run it saying so, so an agent neither asks for nor assumes provider permission |
| 9 | Activation and switch-on | `CONTEXT.md` "Rule Activation Approval"; `CLAUDE.md` "Talking with the operator" | Gap: the gate did not say what passing it grants | Gate: passing grants no approval, access change, activation or switch-on |
| 10 | Completion wording: the gate counted only FAIL, so NOT_TESTED controls and `-` gaps on a touched platform had no place in its record | `CLAUDE.md` "Task checklists" (report "incomplete"); the ticket's completion rule (a not-applicable phase needs evidence, not a false PASS) | Gap | Gate: its record names each NOT_TESTED control and `-` gap, and none counts as a pass. A change that touches no platform's access records the gate as not applicable with its reason, never PASS. An open FAIL with no acceptance stops the finalising |
| 11 | Report "scope and evidence date" | `CLAUDE.md` "Talking with the operator": every time shown is ET | Gap: time zone unstated (AWS and Snowflake report UTC) | "date and time in ET" |
| 12 | Configuration only | data-onboarding hard stop; operator memory "Configuration only" | Not applicable: access-audit onboards no source. "Add a platform" is a code change done under a ticket that asks for it | No change |
| 13 | Test-scenario approval: "Add a platform … add its clean case and one weakness per objective" to the tests | The map's execution note (proposed scenarios need the operator's approval); `CLAUDE.md` "Writing a test" | Consistent: standing guidance for a future code change, not a test added here | No change; no scenario or test code added |
| 14 | Local proof: no live test is NOT_TESTED; the empty or refused view is NOT_TESTED | `CLAUDE.md` "Stay close to reality" | Consistent | No change |
| 15 | Work lean; "do not repeat a run only to recreate its report" | `data-platform` "The seven wastes"; `CLAUDE.md` "Long steps and runs" | Duplicate, consistent; already a pointer | No change |
| 16 | The auditor never fixes; the fix belongs to the platform's operations skill | Ticket 79's handoff table | Consistent | No change |

Findings outside this skill's files (not edited here):

- `aws-snowflake-operations` "Fixing an access finding" step 3 and
  `access_remediate.py apply --words` require "the operator's exact words"
  before an access apply. `CLAUDE.md` says to record a step's approval as given
  and to stop only for a switch-on or a new kind of decision. Which rule
  governs an access-change apply is open decision A below, for ticket 92.
  The script stays unchanged: this ticket authorizes no code change.
- `data-operations/HOSTED-LOADS.md` role guards consume the CST, TMO and LOG
  findings; no conflict found. Nothing to hand to ticket 56.

## Open decisions

- **A. Approval words for an access change.** This is ticket 02's decision A
  applied to access: "do not ask for approval, record it as given" against
  "the operator's exact words" for the Snowflake access apply. Access audit
  applies nothing, so it does not settle this. The skill's own rule (row 5)
  covers only risk acceptance, which the skill already reserved to the
  operator. Needs the operator's ruling, or ticket 92.

## Traces

These are readings of the changed text, not audit runs.

- **Routine path:** a skill change that edits wording only and creates no role,
  login, grant, credential, connection or audited setting. The gate records
  "not applicable: the change touches no platform's access", never PASS. No
  audit runs, no approval is asked or recorded, no provider is contacted, and
  nothing is switched on.
- **Blocked path:** a new Snowflake service role whose `snowflake` audit
  shows an LPR FAIL with no acceptance in its ticket. The
  gate stops the finalising. The agent names the finding (control, counts, the
  fix it names), the decision and a recommendation to the operator, as one
  question. It cannot write the
  acceptance itself (hard stop, row 5), and it does not apply the fix: the fix
  goes to `aws-snowflake-operations`, whose apply has its own approval
  (open decision A). Neither the stop nor the handoff grants approval, access
  change or switch-on.

## Answer

Access audit's hard stops name each shared rule's home and grant no
permission. The rule that conflicted (a "signed acceptance" that an agent could
record as given) is reserved to the operator's own words, as a new kind of
decision. The gate records what was not tested, records "not applicable" for a
change that touches no platform's access, stops on an unaccepted FAIL and
grants nothing. Run it routes AWS and Snowflake runs to their skill and login
files to `CONNECTIONS.md`. No skill edit is needed for this ticket: the
current `origin/main` skill already contains these dispositions and handoffs.

The approval words for an access-change apply remain unresolved. Access audit
does not remediate, and the question is carried to ticket 92 without deciding
it; ticket 08's profiling-specific operator ruling is not applied to access
changes.

Changed: this ticket's evidence record only. The skill artifact is
[skills/access-audit/SKILL.md](../../../skills/access-audit/SKILL.md), unchanged
by this ticket.

Prerequisites: current `origin/main` (`711bad7`) records tickets 02 and 79 as
resolved. Ticket 02 records that routine-approval wording remains an open
operator decision; ticket 79 assigns access remediation to the owning
operations skill. The current skill has been checked against those
dispositions.

Provenance: reviewed the repository skill from `origin/main` at
`711bad7dd119637417db65d7ae398f0803f1157f` (SHA-256
`8ef6c59731b193b6f8eea0bfc215ef847bafef21775a21f321fb34219684c1e1`).
No installed `access-audit/SKILL.md` exists under `~/.agents/skills`; the
repository copy is the applicable artifact. Read the installed `write-skill`
guidance through `skill://write-skill`; its edit-ladder advice supports making
no skill change when the required behavior is already present.

No live audit, access change, provider request, or switch-on was performed.

## Validation

- Re-read the ticket inventory and current `origin/main` skill. The skill's
  Hard stops, Start here, Decisions/artifacts/handoffs, Rating/report, and gate
  sections implement the dispositions in the inventory; the existing routine
  and blocked traces remain consistent with those boundaries.
- Confirmed `02-data-platform-consistent-rules.md` and
  `79-access-audit-responsibility.md` are `resolved` on current `origin/main`;
  the former carries routine-approval decision A, and the latter keeps
  remediation separate.
- First-head CI for [PR #2011](https://github.com/paulananth/edgartools-platform/pull/2011)
  passed all 12 jobs on commit `55c184410fc87fd8b950f7e3eac0b84f0345a756`
  ([run #44968140505](https://github.com/paulananth/edgartools-platform/actions/runs/44968140505)).
  Current-head CI will be checked again after the completion-record commit.
- No local tests were run in this phase. The scoped artifact change is a
  ticket record only.


## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
