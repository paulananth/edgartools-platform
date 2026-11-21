# mdm-engineering: Define one responsibility

Type: task
Status: open
Priority: P2
Blocked by: 01, 13
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [mdm-engineering](../../../skills/mdm-engineering/SKILL.md)
Step: 1 of 6
Skill dependencies: data-modeling
Applicability: Conditional: choose mastering proof or investigate a demonstrated engine or storage gap; configuration remains the default.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Own merge and storage behavior and proof selection; do not turn a source mapping task into an engine refactor.

Inventory existing instructions against the neighboring owners: data-onboarding or refining-rules when configuration suffices; separate implementation work for a real gap. Reconcile the current index and references before moving any text.

Start from skills/mdm-engineering/SKILL.md: Hard stops, Choose the cheapest proof, Independent installed qualification. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md)

Priority rationale: Conditional mastering proof or demonstrated engine gap.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence; verified against the current MDM Engineering scope, merge/storage sections and proof guidance, and recorded in [Decisions, artifacts and handoffs](../../../skills/mdm-engineering/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 19:38 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff; verified against Data Onboarding, Refining Rules, Data Modeling, Data Operations, Bookkeeping and Production Support references in the ownership table. (2026-11-20 19:38 ET)
- [x] Demonstrate the boundary on a conflicting identifier, a relationship with a missing endpoint and a merge retry after interruption; documented walkthrough links retained work rather than duplicating it. These links identify existing behavior coverage; no scenario was executed and no behavior claim is made from this documentation check. (2026-11-20 19:38 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: configuration is the default when the existing engine can express requested behavior; MDM Engineering changes require a demonstrated reusable engine or storage gap. Recorded in [Decisions, artifacts and handoffs](../../../skills/mdm-engineering/SKILL.md#decisions-artifacts-and-handoffs). (2026-11-20 19:38 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Answer

MDM Engineering owns reusable merge behavior, durable MDM storage, adapter
operations and migrations, and proof selection for a demonstrated engine or
storage change. Its inputs are the configured policy or contract, evidence of
a behavior gap the existing engine cannot express, and the selected engine's
requirements. Its outputs are shared engine or adapter changes, any required
migrations, and qualification evidence. The ownership table and handoffs are
in [Decisions, artifacts and handoffs](../../../skills/mdm-engineering/SKILL.md#decisions-artifacts-and-handoffs).
Configuration stays the default when existing behavior can express the
request; MDM Engineering does not turn a source mapping task into an engine
refactor.

Documented boundary walkthrough, using retained checks rather than adding
scenario or test code:

| Case | Existing evidence | Owner and outcome |
|---|---|---|
| Conflicting authoritative identifiers | [`test_identifier_lists.py`](../../../tests/mdm/test_identifier_lists.py) asserts `authoritative_identifier_conflict`; [`test_mastering_registrant_lei.py`](../../../tests/storage_adapters/test_mastering_registrant_lei.py) checks that the conflict remains a review across storage adapters. | Data Modeling decides identifier meaning and contract; Data Onboarding or Refining Rules configures it. MDM Engineering owns the shared merge outcome and adapter persistence. |
| Relationship whose endpoint has no master | [`test_mastering.py`](../../../tests/storage_adapters/test_mastering.py) checks `unresolved_endpoint`, then resolves it after the endpoint master is added. | Data Modeling owns relationship meaning and endpoints; configuration is supplied by Data Onboarding or Refining Rules. MDM Engineering owns endpoint resolution in merge/storage behavior. |
| Interrupted merge waiter release and retry | [`test_pair_evidence_keys_and_waiter_release_roll_back_together_and_retry_completes`](../../../tests/storage_adapters/test_mastering.py) asserts rollback, retry completion and unchanged repeat behavior. | MDM Engineering owns atomicity and retry behavior across the storage adapters. |

These links locate existing tests; they were not run for this ticket, and
reading their names or source is not a substitute for executing behavior
checks. The documentation genericity check only checks generic skill wording.

Baseline evidence: `origin/main` resolves to prerequisite commit
`4881e8322909888860db576f65730bc4889dc5a4`, and that commit is an ancestor of
this branch. The installed `~/.agents/skills/mdm-engineering` and
`~/.claude/skills/mdm-engineering` links point to
`/Users/aneenaananth/projects/edgartools-platform/skills/mdm-engineering`, a
different checkout; its skill differs from this repository copy. The current
repository `origin/main` copy was used as the source of truth. The installed
`write-skill` guidance was read from `~/.agents/skills/write-skill/SKILL.md`;
its provenance tool reported `mdm-engineering` as a user skill with no
`Skill-Diet` baseline.

Validation:

- `UV_CACHE_DIR=/private/tmp/ticket37-uv-cache uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_skills_cite_no_ticket.py tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py` — **150 passed**. This covers documentation genericity, cited-path existence, ticket-number restrictions, skill length and guide paths; it does not verify ownership or behavior. The first run caught the 500-line skill limit; the skill was shortened to 495 lines and the check passed on rerun.
- `git diff --check` — clean.
- `~/.agents/skills/gstack/bin/gstack-skill-bill mdm-engineering` — reported the installed user skill through its symlink to the other checkout, with no `Skill-Diet` baseline. It did not measure this worktree's edited file. This worktree's `SKILL.md` is 36,152 bytes before and 38,150 bytes after, per `git show HEAD:skills/mdm-engineering/SKILL.md | wc -c` and `wc -c skills/mdm-engineering/SKILL.md`.
- No behavior scenario or MDM tests were run; the three linked tests are retained work, not evidence of a newly executed behavior check.

## Remaining work

- Publication and the affected repository checks remain unchecked because the
  user explicitly prohibited creating a PR, commit or push. This ticket stays
  open and incomplete until that publication step is authorized and completed.
