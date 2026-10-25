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
- [ ] Publish this skill change on its own PR after its implementation evidence is qualified; follow named merge approval.
- [ ] Learning → skill: name the changed skill sections and their verified evidence.

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
