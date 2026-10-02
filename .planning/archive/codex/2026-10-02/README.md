# Archived Codex workstreams — 2026-10-02

These are historical records from completed or superseded Codex branches.
Their status text, remaining checklists and evidence describe their original
snapshots. Archiving does not establish that deferred qualification or deployment
was completed. Consult the current specifications and mastering task map for
active work.

| Workstream | Retirement evidence |
| --- | --- |
| [Bookkeeping design](bookkeeping-loader-independent-design/TICKET.md) | PR #785 merged; design and skill scope completed |
| [Bookkeeping skill](bookkeeping-skill/STATE.md) | PR #735 merged |
| [Bookkeeping stage work](bookkeeping-stage-work/STATE.md) | PR #734 merged; later implementation supersedes its next frontier |
| [Configured Bookkeeping](configured-bookkeeping/STATE.md) | PR #732 merged; broader replacement was subsequent work |
| [Journal decoupling](change-journal-decoupling/TICKET.md) | PR #794 merged |
| [Fresh Journal](change-journal/IMPLEMENTATION.md) | PR #738 merged; Company-only acquisition superseded broader caller plans |
| [Test reduction](codex-test-reduction-implementation/REVIEW.md) | PR #760 merged; pilot #761 closed without merging |
| [Parser research](custom-parsing-research/TICKET.md) | PR #784 merged |
| [Mastering rebuild](mastering-rebuild/TICKET.md) | PR #780 closed; replacement #781 merged; original incomplete qualification remains historical |
| [Legacy control retirement](retire-legacy-control/RETIREMENT.md) | PR #741 merged |

The original mastering handoff path remains a redirect because the separate
Claude qualification workstream references it. Historical branch URLs in the
archived draft now use the saved commit SHA. Local document links still resolve.
Historical inline paths retain their original snapshot meaning.

## Cleanup record

Codex-only cleanup retired ten local branches, seven remote branches and four
registered worktrees. Nineteen saved refs were restored from the verified Git
bundle into local archive refs, proving recovery. The dirty detached worktree's
15 modified files were preserved and checked by SHA-256; all four worktree
directories, including ignored files, were relocated intact.

Local recovery files are under
`~/.codex/runtime/codex-cleanup-20261002-133159/`. They include the Git bundle,
before/after manifests, dirty patch, retired worktree directories and restoration
instructions. This recoverable retirement does not reclaim those directories'
disk space.

Bookkeeping and Change Journal skill links now resolve to the current main
versions in the cleanup worktree. Before retiring that worktree later, relocate
these links again. Other runtime branches/worktrees and shared dirty files were
excluded; concurrent Claude/Grok edits were observed and left alone. Stashes
were read only and remain unchanged.

See the [cleanup checklist](../../../workstreams/codex-cleanup/TICKET.md).
