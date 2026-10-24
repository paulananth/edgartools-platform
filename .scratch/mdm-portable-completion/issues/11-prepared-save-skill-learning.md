# Preserve assessed-save and owner-activation guidance

Type: task
Status: resolved
Assignee: Codex
Claimed: 2026-10-24 09:38 ET
Parent: [Normal atomic Merge Stage](04-commit-normal-merge-atomically.md)

## Parts

- [x] Record transactional owner activation, assessed intent/producer separation, rollback preview and natural input identities in the owning skill — 2026-10-24 09:40 ET; guidance reviewed against the qualified normal-save and storage cases.
- [x] Verify source-neutral wording and focused skill checks; review Standards, Spec and GoF — 2026-10-24 09:40 ET; 79 focused checks pass in 2.79 seconds; review below.
- [x] Learning → skill: mdm-engineering/references/storage-adapters.md, “Qualify assessed saves and owner activation” — 2026-10-24 09:40 ET; source-neutral guidance preserves separate worker and installed-workflow gates.

## Evidence boundary

These lessons come from the normal-save implementation qualification. They
preserve separate operator-read, worker-authority, recovery and installed
workflow gates. This skill branch changes guidance only and authorizes no
source activation or hosted installation.

## Review

### Standards

Guidance and its checklist only; no runtime, migrations, grants or data change.
Focused genericity checks pass; no source values or concrete source/kind policy
are introduced. The overlap guard and whitespace check pass.

### Spec

The lessons preserve destination-owned enforcement, fresh rebuild/data-migration
requirements, exact assessed intent and original producer, complete rollback,
and configuration-driven proof. A save smoke establishes neither configured
worker support nor the full installed matrix; those gates remain explicit.

### GoF

Keep the existing Adapter and shared Merge Stage preparation. Git history shows
that transport seam changing across the storage/read/save work; factoring its
read and admission behavior there avoids a second merge algorithm. The new
guidance adds no hierarchy or dialect-specific policy strategy. Its maintenance
cost is keeping each qualification boundary beside the operation it governs.
