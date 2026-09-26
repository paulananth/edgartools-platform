# MDM/silver architecture handoff for Claude or the next agent

Date: 2026-09-26. Branch: `codex/mdm-silver-boundary-research`.
Worktree: `/Users/aneenaananth/projects/edgartools-platform-worktrees/codex-mdm-silver-boundary`.
Base refreshed to `origin/main` at `3ea3a6b1`; recheck live refs before continuing.

## Start here

Read the [accepted architecture brief](architecture.md),
[architecture requirements](specification.md) and
[ADR 0016](../../docs/adr/0016-independent-mdm-and-silver-mappings.md).
[Decision replies and verification times](decisions.md) are the approval evidence.
The operator confirmed the complete direction in Q7 (verified 11:11 ET).

Shared parsing produces durable source records preserving all structured fields;
MDM and analytical silver have independent mappings, versions, progress and retries.
Keep current and needed parse versions. Mapping-only changes rerun only affected
work. First prove the boundary on a bounded SEC Company + GLEIF cohort.

## What is complete

- Primary-source research, repository assessment and architecture interview.
- Accepted decision direction and explicit qualification/acceptance requirements.
- Documentation-only checks; no runtime code, migrations, contracts or outputs changed.

The old countryCode omission is historical: PR #720 repaired it before this
branch's final refresh. It illustrates projection coupling, not a current defect.

## Next work

The architecture requirements' **Migration and engineering gates** section is
the remaining frontier. Qualify source-faithful encoding/partitioning, derived
lineage and artifact/control recovery, independent component versions, retention
protection and reproducible bounded proof/cost commands. Prefer existing readers,
publication/adapter and Merge Stage seams. Resolve those gates before issuing
executable implementation tickets; no performance or storage savings are proven.

Amend the Source Contract/glossary explicitly: their current silver-to-MDM wording
does not yet implement the independent source-record boundary. Coordinate ownership
before editing another runtime's source-contract or Company files. Preserve stable
source codes/keys, existing entry points, outputs and rollback capabilities.

Use your own runtime branch/worktree. This handoff permits reading the saved
direction; it is not authorization to commit on Codex's branch. Existing source
retention, MDM atomic journal boundaries and exact matching-rule activation gates
continue to apply. No production deployment or rule activation is approved here.
