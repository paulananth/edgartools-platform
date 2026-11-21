# data-profiling: Reconcile shared rules

Type: task
Status: resolved
Priority: P0
Blocked by: 02, 07
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)
Step: 2 of 6
Skill dependencies: data-platform
Applicability: Every new captured dataset; compare mode only when an approved delivery changes.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: REPORT.md, findings.yaml, fingerprints and invalid-row evidence kept private where required.

Start from skills/data-profiling/SKILL.md: Modes, Profile once, How to work, Compare a new delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [data-profiling: Define one responsibility](./07-data-profiling-responsibility.md)

Priority rationale: Reusable evidence is the input to every source model.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition; verified by document review of `CLAUDE.md`, `CONTEXT.md`, the data-platform and data-onboarding hard stops, the data-profiling skill and `docs/specs/profiling/findings.md`, plus a code reading of `profiling/run.py` and `profiling/quality.py` (masking); recorded under [Inventory](#inventory). (2026-11-20 18:29 ET)
- [x] Align the local phase with the shared rule decision while preserving explicit operator boundaries; verified by document review of the diff to `skills/data-profiling/SKILL.md` (Hard stops, "Profile once", How to work step 1) against the inventory. The approval boundary is unchanged. (2026-11-20 18:29 ET)
- [x] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred; verified by document review under [Traces](#traces). No profile, compare or approve command was run. (2026-11-20 18:29 ET)
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. [PR #1972](https://github.com/paulananth/edgartools-platform/pull/1972) merged with all 12 CI checks passing. (2026-11-21 12:10 ET)
- [x] Open decision A resolved by the operator on 2026-11-21: keep explicit approval for findings and designed keys; the user asked for a private, sanitized Archify review view before approval. The view is not consent; `approve --words` remains the approval record. (2026-11-21 12:10 ET)
- [x] Learning → skill: evidence files stay on the machine and only the names/counts catalog summary is public; present in [Hard stops](../../../skills/data-profiling/SKILL.md#hard-stops). (2026-11-21 12:10 ET)

## Inventory

Authority order (ticket 02): explicit operator instruction, then `CLAUDE.md`,
then `CONTEXT.md` definitions, then the owning skill. Ticket 02's disposition:
a rule list names each shared rule's home and grants no permission.

| # | Local instruction (data-profiling) | Authoritative source | Finding | Disposition |
|---|---|---|---|---|
| 1 | Hard stop "Approve findings for the operator…"; How to work steps 4–5 (ask, record exact words); narration "Approval still comes only from the operator's exact words" | `CLAUDE.md` "Talking with the operator" ("Do not ask for approval… record it as given"); `profile_data.py approve --words` (required) and `compare` (refuses unapproved findings) | Conflict, the same as ticket 02's open decision A | The text and code are unchanged. The row now notes that `compare` enforces the approval. Open decision A below |
| 2 | Hard stop "Request anything from a provider's website" | `CLAUDE.md` "Commits, PRs and secrets": no request to a provider (site, API or documentation) without permission for that request; data-platform hard stops | The scope covered only the website. The skill is stricter in permission: it never makes a request | Widened to site, API or documentation. The phase rule is kept: profile local copies only, and name a provider-only fact to the operator as a blocker. No path "with permission" was added |
| 3 | Hard stop "Print or keep a database address, a password…"; "samples are masked to their shape" | `CLAUDE.md` secrets rule; data-platform hard stops ("read from configuration, never print") | Consistent on secrets. "Samples are masked" overstated the masking: only a personal column's samples are masked (`run.py` `top`, `quality.py` examples) | Cited to data-platform. The masking claim was corrected to "a personal column's samples" |
| 4 | Outputs `REPORT.md`, `findings.yaml`, `invalid_rows.jsonl`, `fingerprints.json`, `drift.yaml`: no rule on where they may go | `CLAUDE.md` "This repository is public: counts and invented examples only"; data-platform Source readiness ("keep qualification artifacts private and report counts publicly"); the findings spec (short keys can be found again from their hash; absolute input paths in `profiled_with`) | Gap: these files hold values from the data, and no instruction keeps them out of the repository | New hard stop: keep them on the machine. Only `catalog`'s `profile.yaml` (names and counts) is public. `git ls-files` shows none committed |
| 5 | "A gap in what the profiler measures is a profiler fix with its own ticket" | data-onboarding hard stop "configuration only: write the ticket, ask before coding" | Conflict: no gate before coding | New hard stop row, and "Profile once" now says the ticket is written before any code |
| 6 | How to work step 1 "Ask what the data set is called and where its copies are" | data-platform routing (hand the retained capture location to the next owner); `CLAUDE.md` "Decide what follows from a ruling" | Conflict: it asked again for what the caller had already handed over | Start from the handed-over location, and ask only when there is none and no local copy fits |
| 7 | Hard stop "Ask several questions at once" | data-onboarding hard stop; `CLAUDE.md` "ask one question at a time with your recommendation" | Duplicate | Cited to data-onboarding |
| 8 | Hard stop "Start a long pass silently" | `CLAUDE.md` "Long steps and runs" (state the time, `run_sample.py`, report elapsed time for steps over ten minutes) | Partial duplicate | The phase detail is kept (the run prints size and estimate). The rest points to `CLAUDE.md` |
| 9 | Hard stop "Pin a finding on one source or one domain" | `CLAUDE.md` "Build generic" | Duplicate, consistent | Cited |
| 10 | Draft code set and new kind: "only the operator approves" | `CONTEXT.md` "Rule Activation Approval"; the ticket 07 handoff table (Data Modeling, Data Onboarding) | Consistent | No change |
| 11 | Exposure: "grants no access, applies no live tag, creates no mirror" | data-platform `FINAL-TABLES.md` | Consistent: no activation authority | No change |
| 12 | Local proof: "Choose a proof sample by kind"; Profile once / reuse | `CLAUDE.md` "Long steps and runs", "Stay close to reality"; mdm-engineering "Choose the cheapest proof" | Consistent; this is the phase method other skills link to | No change |
| 13 | Test-scenario approval | The map's execution note | data-profiling holds no scenario rule | No change. No scenario or test code was added |
| 14 | Completion wording: "measured" against "not yet tested" (narration) | `CLAUDE.md` "Task checklists"; data-onboarding "explored, checked or loaded" | Consistent. The narration section changes only on the operator's instruction | No change |
| 15 | `CODE-SETS.md` step 4: `rdm approve … --words "<their exact words>"` | `CONTEXT.md` "Rule Activation Approval"; `CLAUDE.md` "Do not ask for approval" | The same conflict as row 1 | Covered by open decision A. The file's move is deferred to tickets 19 and 13, so it is not edited here |
| 16 | `SOURCE-RANKING.md`: "It writes names and counts only, so the files may go in the repository" | `CLAUDE.md` public-repository rule | Consistent with row 4: ranking output holds no data value | No change. Row 4 names only the files that hold data values, so it does not cover ranking output |

The data-onboarding hard stops still say "a provider the operator has ruled
out" and "read, print or paste a secret" (ticket 02's rows 5 and 6). They
belong to ticket 20 and are not edited here.

## Decision

- **A. Routine approvals, this skill's part — resolved 2026-11-21.** The operator chose explicit approval for findings and designed keys. A private Archify review view is a read-only aid before the request, not consent; `approve --words` must still record the operator's exact words, and `compare` still refuses unapproved findings. A proposed new kind remains a new decision for Data Modeling and the operator. The view implementation belongs to the next Data Profiling entrypoint ticket.

## Traces

These are readings of the current text, not runs.

- **Routine path:** Data Onboarding hands over a retained capture location.
  Profiling starts from it without asking. `run` profiles the local copies
  once, or prints `reused`. The story is told as counts. The questions
  (designed key, new kind) go one at a time, each with a recommendation. The
  report is shown, and `approve` records the operator's own words only when
  they give them. The folder is handed to Data Onboarding and Data Quality.
  The evidence files stay on the machine, and only `profile.yaml` reaches the
  repository, through Data Onboarding. No provider request, no switch-on and
  no approval on the operator's behalf is part of this path.
- **Blocked path:** refining-rules asks for `compare` on findings that were
  never approved. `compare` refuses them. The way forward is the operator's
  own approval, never an `approve` with words they did not say. If the copies
  are not on the machine, a capture is a provider request that needs its own
  permission, so name the blocker and stop. If the profiler cannot read a
  table, list it under `dataset.not_read`, and write a ticket for the fix
  before any code. None of these steps grants approval, provider access or
  switch-on.

## Answer

Data Profiling's hard stops now name each shared rule's home and grant no
permission. The skill now:

- keeps its evidence files private, and says why;
- covers a provider's API and documentation as well as its website, while
  still making no request of its own;
- corrects its masking claim;
- gates a profiler code fix behind a ticket;
- starts from the capture location it was handed.

PR #1972 merged the rule changes with all 12 CI checks green. The operator resolved decision A: explicit approval remains, and a private Archify view is only a review aid, not consent. The view and focused master-entity discovery are being implemented in the next Data Profiling entrypoint ticket.

Provenance:

- **Baseline.** `HEAD` and `origin/main` are both `30ae0e7b` (ticket 79,
  PR #1968).
- **Prerequisites.** `git merge-base --is-ancestor` exited 0 for
  `e166fa56` (ticket 02, PR #1966) and for `6c5c5393` (ticket 07, PR #1969)
  against `origin/main`. Their ticket files were not edited.
- **Installed copies.** Both aliases resolve to the main checkout's `skills/data-profiling`. The installed file differs from the current repository copy (514 versus 497 lines); it was left untouched. This closeout changes only the repository ticket.
- **write-skill guidance.** Read during this closeout; no skill file is edited by this status update.

## Validation

- Original PR #1972 docs checks: `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py` — **149 passed** after each edit. These check wording, genericity and guide paths; not approval or routing behavior.
- Closeout check: `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py` — **142 passed**; `git diff --check` clean. This check does not exercise approval or routing.
- `skills/data-profiling/SKILL.md` was 462 lines at PR #1972 validation; the repository copy is 497 lines at this closeout.
- Placement of evidence files: a `grep` for `findings.yaml`, `REPORT.md`, `drift.yaml`, `invalid_rows` and `RANKING` across data-onboarding, refining-rules, data-quality and the profiling sub-files found no instruction to commit them. The onboarding log records only the findings' path. `git ls-files` lists none of the five files.
- The new links (`../data-platform/SKILL.md#hard-stops` and `../data-onboarding/SKILL.md#hard-stops`) were checked by hand against those files' `## Hard stops` headings.
- The local `tests/unit/test_skill_bundle_portability.py` run was skipped because the original worktree had no synced environment; PR #1972's full CI suite passed all 12 checks.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
