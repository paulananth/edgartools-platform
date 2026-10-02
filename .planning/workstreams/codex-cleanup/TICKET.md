# Clean old Codex branches and workstreams

Owner: Codex. Status: complete — local cleanup verified; planning archive PR #797 open. Branch: `codex/cleanup-old-workstreams-20261002`.
Scope: old Codex refs, worktrees and completed or superseded Codex planning.
Preserve other runtimes, active work, dirty files, stashes and runtime skills.

## Checklist

- [x] Inventory live local/remote Codex refs, PR status, worktree dirtiness and workstream ownership. — live refs, PR metadata, worktree status and ownership checked; 2026-10-02 13:44 ET.
- [x] Save verified recovery bundles/manifests and archive any retained files before removing old refs or worktrees. — 252,925-byte bundle verified; 19 refs restored; four directories and cm12 binary patch retained; 2026-10-02 13:44 ET.
- [x] Relocate installed Bookkeeping/Change Journal skill links before retiring their old worktrees. — current main skills resolve; both link installers pass idempotently; Bookkeeping #788 update retained; 2026-10-02 13:44 ET.
- [x] Remove eligible old Codex local/remote branches and worktrees; verify other runtimes are unchanged. — 10 local and 7 remote refs retired with SHA checks/atomic remote leases; four worktrees relocated; non-Codex refs excluded; 2026-10-02 13:44 ET.
- [x] Archive completed/superseded Codex workstreams with references preserved; retain active/shared/uncertain ownership. — 10 folders / 21 tracked files archived; historical pending items retained; Claude handoff redirect preserved; 2026-10-02 13:44 ET.
- [x] Verify restoration, skill discovery, links, preserved shared dirtiness and final inventories. — 36 local Markdown links checked; 19 restored SHAs and 15 dirty-file hashes match; shared protected hashes/stashes match; concurrent other-runtime edits left alone; 2026-10-02 13:44 ET.
- [x] Commit/push the planning cleanup and create a review PR. — published 2e8ed941; GitHub confirms PR #797 open against main with matching head; 2026-10-02 13:47 ET.

## Evidence and limits

Base: `b6474bf24c8d2bd275c921220977d68ef9959c06`. Old Codex PR discovery
found no open PRs. PRs #738, #741, #784, #785 and #794 were verified merged;
#761 was closed without merging; #780 was closed and superseded by merged #781.
Recovery branches without PRs were saved before removal.

Recovery: `~/.codex/runtime/codex-cleanup-20261002-133159/` contains the verified
bundle, manifests, 15-file dirty patch, intact retired worktree directories and
restoration instructions. Archive refs retain the saved objects locally. This
retirement does not reclaim the preserved directories' disk space.

The new cleanup branch is the only active Codex branch. Claude/Grok branches,
worktrees and workstreams, shared `fix-pipelines`, both protected dirty files
and stashes were excluded. Concurrent Claude/Grok dirty status changed during
verification; those changes were not touched. The old mastering handoff path
is a compatibility redirect, not an active Codex assignment.

No runtime code, tests, migrations or deployment configuration changed. Local
verification covers document links, preserved contents, JSON, skill resolution,
exact Git recovery, branch inventory and protected file hashes. Full runtime
pytest was not repeated for these planning moves; GitHub CI remains enabled.
The inventory and recovery work took about 17 minutes before final publication.

PR: https://github.com/paulananth/edgartools-platform/pull/797. Merge is outside this task.
