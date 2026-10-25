# Preserve original provenance in portable consumer reads

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-24 20:14 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 05 qualification and implementation landing

## Parts

- [x] Review the demonstrated read failures and existing guide for the smallest reusable lesson — 2026-10-24 20:14 ET; ticket 05 proves metadata lookup, replay provenance and coherent snapshots on both engines, with counts/outcomes only.
- [x] Add source-neutral guidance for metadata parsing, original producer/time, coherent snapshots and truthful unsupported routes — 2026-10-24 20:15 ET; the skill points to its retained-read provenance section.
- [x] Validate guide references, genericity and affected skill checks; review Standards, Spec and GoF — 2026-10-24 20:15 ET; 80 affected checks pass and the new reference anchor resolves.
- [x] Publish this skill change on its own PR after its implementation evidence is qualified — 2026-10-24 20:56 ET; draft PR #1165 links reader PR #1164, whose two-kind/source installed reader checks pass on both engines.
- [ ] Observe rebased skill checks, reconcile implementation landing and follow named merge approval for #1165.
- [x] Add source-neutral configured name search, coverage gaps, bounded owner rebuild and driver statement-count guidance — 2026-10-25 12:24 ET; 91 affected guide/genericity/command checks pass.
- [x] Qualify the documented command against the new independent installed search checkpoint — 2026-10-25 12:27 ET; independent ca2f6f75 five-wheel installation passes normal search, gap refusal and actual owner CLI resume/zero-work repeat for both configured kinds on PostgreSQL/MySQL.
- [x] Diagnose and qualify the installed guide/command dependency — 2026-10-25 13:07 ET; both exact failed doctor cases pass through independent stacked five-wheel build 58933e0c.
- [x] Learning → skill — 2026-10-24 20:56 ET; mdm-engineering points to storage-adapters.md, Retained-read provenance, for original metadata bytes, applied producer/time, coherent snapshots, stable page cursors and explicit unsupported routes.

## Evidence boundary

The implementation checkpoint is 8e15a9ee on the dedicated reader branch.
Two configured kinds pass identifier/cross-reference lookup and historical
Context cases on each engine. A native JSON scalar probe rejected a valid
401-digit integer on MySQL; parsing original bytes fixes that case. A
competing save preserves a coherent answer, followed by a fresh one, on both
engines. Duplicate replay preserves original producer and recording time.
Independent installed-reader qualification is still pending. This document
and the guide do not declare the full workflow or name search supported.


## Review — 2026-10-24 20:15 ET

### Standards

Fresh dedicated branch/worktree from main. Source-neutral guidance, no runtime
or provider requests, public counts/outcomes only. Eighty affected genericity
and skill-command checks pass; the new local link target exists.

### Spec

The guide captures demonstrated reader lessons without claiming full workflow
support or installed-reader qualification. Publication waits for the reader
implementation evidence; this ticket remains incomplete.

### GoF

Documentation only. The guidance retains the existing adapter/reader seam and
existing timestamp authority. It adds no pattern, hierarchy or duplicate
computation. Its value is an explicit completion test for each observed read
failure; details remain behind the existing storage reference pointer.

## Installed evidence update — 2026-10-24 20:56 ET

The independent 8e15a9ee five-wheel runtime passes two configured-kind/source
cases per engine for assessment/save/replay, original provenance, revisions,
aliases/reversal, historical details and relationships, pinned pages and the
actual restricted-role Context/inspection CLI. Six installed reader/adapter
files match the local qualified files byte for byte. A later forced-publication
refusal is separately qualified locally and remains an unimplemented workflow.
The original 80 skill checks and their rebased run pass. Full worker workflow
support remains unclaimed; name-search qualification is recorded below.


## Search guidance checkpoint — 2026-10-25 12:24 ET

Implementation PR #1164 now publishes ca2f6f75. Local search/rebuild cases pass
for two configured kinds on PostgreSQL/MySQL, including stale coverage, owner
permissions, interruption and explicit restart. New bulk maintenance proof
checks 401 inserted references and mixed updates/deletes in three driver
statements each. The guide records the bounded owner command, readiness and
zero-work retry checks, and the independent-install completion boundary.
Ninety-one affected documentation checks pass. Installed search and final
CI remain pending; no full worker publication support is claimed.

### Standards

Separate skill branch and PR; generic terminology and invented examples only.
Overlap guard and whitespace pass. No runtime or migration changes here.

### Spec

Documents the demonstrated coverage and rebuild gaps and the exact normal
owner command. Keeps qualification, activation and worker publication separate.

### GoF

Retains the existing adapter and shared-function boundary. Documentation adds
no classes or alternate computation; maintenance statement counts expose the
measured cost that the implementation removed.


## Installed command evidence — 2026-10-25 12:27 ET

Two configured-kind/source cases per engine pass outside the checkout through
the committed ca2f6f75 five-wheel installation. The actual owner command
repairs a missed index generation in two one-master pages, reports ready,
then repeats with zero work. Normal search works afterward; business counts
and generation stay unchanged. The documented command is now independently
qualified on PostgreSQL/MySQL. Final skill CI and named merge approval remain
open. Learning is in mdm-engineering, Governed name-index rebuilding.


## Capability wording reconciliation — 2026-10-25 12:34 ET

Removed stale blanket MySQL caller refusals from the skill introduction and
governed installation reference. The wording now names the independently
qualified assessment/save/replay and read/search operations, while retaining
the unqualified full worker/publication boundary. All 91 affected checks pass
again. This documents operation-specific evidence; it does not activate work.


## Installed doctor dependency resolution — 2026-10-25 13:07 ET

The original skill-only head correctly failed two installed doctor checks:
its guide named the new command, but its main-based runtime lacked #1164.
Rebase the skill branch on the implementation and compare only its five
documentation files; keep the implementation PR head unchanged while its
merge approval is pending. Independent stacked five-wheel build 58933e0c
completed in 352.19 seconds. Both exact failed tests now pass (16.16 seconds):
`test_doctor_passes_from_the_installed_bundle` and
`test_doctor_names_a_command_no_skill_may_write`. The database fixture cleans
up its temporary PostgreSQL server; no assertion was relaxed.

The current workflow runs PR CI only against main. Therefore the stacked
skill PR has no new full-CI claim. After approved #1164 merges, rebase the
skill commits onto that main, retarget #1165 to main, observe all nine CI
checks and obtain named approval before merging #1165. Those gates remain
unchecked. The installed build differs from the current branch only in
tracker documentation.
