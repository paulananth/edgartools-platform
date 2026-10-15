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

- [x] Rebase this clean, unpublished branch onto freshly fetched main and verify preserved changes — clean rebase onto82f4e5ce; range-diff shows both original/intake commits unchanged; 0 behind/2 ahead after a second fetch; original9d3dfeba retained in the verified private cleanup bundle; 2026-10-14 21:51 ET.
- [x] Refresh the responsibility plan against current Rust kernels, Merge Stage behavior, storage-first ruling and canonical architecture guidance; correct stale snapshot claims in docs/architecture/runtime-responsibilities.md after ownership validation — current native/caller source and migrations019/020 checked; removed snapshot/load_closure guidance corrected, existing native ports acknowledged, P1 authority qualification kept separate; prospective canonical-path guard passed before editing; 2026-10-14 21:56 ET.
- [x] Verify source links, design/history evidence, skill impact and focused checks; run the ownership guard — 90 local links,6 facade entry points,9 caller symbols and4 migration/lock/effects source assertions validated; two focused `--testmon` tests passed in4.32s; GoF/source history reviewed, no skill capability changes; diff check and four-file overlap guard passed; evidence in VERIFICATION.md; 2026-10-14 21:56 ET.
- [x] Verify the current contract3 publication path and distinguish SQL payload preparation from the earlier native contract2 port — migration018/020 and payloads.payload_bytes checked; plan/map corrected; updated validation resolves91 local links,6 facade entry points,9 caller symbols and6 migration/caller source assertions; corresponding skill correction isolated separately; 2026-10-14 22:01 ET.
- [ ] Publish the completed planning branch and create a reviewable PR with verification evidence.
- [x] Learning → skill — skills/data-platform/SKILL.md, Master publication paragraph, corrected in separate [PR979](https://github.com/paulananth/edgartools-platform/pull/979): contract2 preparation is native while contract3 takes SQL-built payload_text;24 platform command examples resolve, focused role test/source checks pass, approval/activation procedures preserved; 2026-10-14 22:02 ET.
