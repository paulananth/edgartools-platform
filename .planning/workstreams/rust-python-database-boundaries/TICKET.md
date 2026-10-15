# Rust, Python, and database responsibility plan

One goal: decide where platform work belongs in Rust, Python, and the database, including which existing database computation can safely move into application code.

Scope: architecture planning grounded in current source and history. Implementation and deployment belong to later execution tickets.

## Planning checklist

- [x] Create an isolated Codex branch from refreshed origin/main and preserve unrelated work. Verified git fetch/worktree output and clean initial worktree at 51b45916; 2026-10-11 14:01 ET.
- [x] Inventory representative Rust, Python, PostgreSQL, and Snowflake responsibilities with source references. Verified source reads and responsibility matrix in PLAN.md; 2026-10-11 14:06 ET.
- [x] Review current design and relevant change history using gof-refactor-reviewer. Verified facade, bridge, Merge Stage and lookup history; retain existing seams, no new pattern hierarchy; 2026-10-11 14:06 ET.
- [x] Classify database work as movable computation, conditional candidate, or required database enforcement. Verified migrations 006/012/013/014/015, destination guard, rule approval and journal checks; classification in PLAN.md; 2026-10-11 14:06 ET.
- [x] Write an execution sequence with correctness, concurrency, performance, and rollback gates. Verified seven planned stages and existing coverage targets in PLAN.md; 2026-10-11 14:06 ET.
- [x] Verify plan references, re-read the checklist, and run the overlap guard. Full-path reference script and git diff --check passed; guard reported no overlap for both planning files; checklist has no unfinished planning parts; 2026-10-11 14:07 ET.

Planning complete. Runtime implementation, benchmarking and deployment are subsequent work described in PLAN.md, and have not been performed by this ticket.

## Rebase and completion requested 2026-10-14

Status: in progress. Complete and publish this architecture-planning ticket;
future runtime execution remains separately scoped.

- [ ] Rebase this clean, unpublished branch onto freshly fetched main and verify preserved changes.
- [ ] Refresh the responsibility plan against current Rust kernels, Merge Stage behavior, storage-first ruling and canonical architecture guidance.
- [ ] Verify source links, design/history evidence, skill impact and focused checks; run the ownership guard.
- [ ] Publish the completed planning branch and create a reviewable PR with verification evidence.
- [ ] Learning → skill — record the existing guidance reused or a newly qualified skill change.
