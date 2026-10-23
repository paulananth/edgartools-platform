# Continue MDM, RDM and Silver after PR #1121

PR #1121 merged at `f001c3c4` after all nine CI checks passed. PR #1120
was closed as covered; its installation fix is identical to the merged file.
The broader portability checklist in `01-migrate.md` remains open.

## Cleanup and continuation checklist

- [x] Inspect ownership, branch/PR state, local changes and installed-skill links; preserve active worktrees of other runtimes — live Git/GitHub inventory; 2026-10-22 19:47 ET.
- [x] Create fresh branch `codex/mdm-rdm-silver-completion-20261022` and its dedicated worktree from `origin/main` at `f001c3c4` — live branch/ref check; 2026-10-22 19:47 ET.
- [x] Save the ten old Codex branch refs in a verified recovery bundle — `git bundle verify`; 2026-10-22 19:47 ET.
- [x] Archive seven old Codex worktrees, including unfinished drafts and ignored files — full archive integrity and all 85 modified/untracked file fingerprints verified before removal; 2026-10-22 19:50 ET.
- [x] Remove seven archived old worktrees and ten saved local branches — paths, registered worktrees and refs independently checked; parked stash and other runtimes preserved; 2026-10-22 19:50 ET.
- [x] Remove four completed remote branches — exact saved-head leases, atomic push and live refs verified; 2026-10-22 19:50 ET.
- [x] Verify fresh branch starts at current origin/main and has its own published upstream — live refs and branch push verified; only this handoff note is new; 2026-10-22 19:50 ET.
- [x] Learning → skill: none; existing recoverable-cleanup and dedicated-worktree guidance applied; 2026-10-22 19:50 ET.

## Next implementation scope

Continue the unchecked work in `01-migrate.md`, prioritizing normal MDM,
RDM and Silver behavior on PostgreSQL and MySQL. SQL Server is last.
Configuration owns entity/source choices; shared programs compute and the
selected database enforces atomic writes, current state, uniqueness and grants.

Remaining work includes the normal MySQL MDM caller, generic candidate routes
and comparison choices, RDM search parity, and the remaining Silver types,
partition indexes and real master-ID integration. Check live ownership and
`overlap_guard.sh` before selecting files; active work by other runtimes is
preserved. Captured onboarding/proving and operational activation remain later
gates. No provider requests or operational store changes are authorized here.

Recovery archives and original-draft snapshots are retained privately. They
are local recovery evidence, not public source-data artifacts.
