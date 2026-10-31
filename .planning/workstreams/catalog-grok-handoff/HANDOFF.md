# Catalog handoff to Grok

Requested by the operator on 2026-10-30. This is an incomplete implementation
handoff, published as a draft PR. No message was sent to an external agent.

## Resume here

Use a fresh `grok/<topic>` branch and dedicated worktree. Read `AGENTS.md`,
`CONTEXT.md`, `skills/data-catalog/SKILL.md` and its model/OpenMetadata references.
The parent ticket is
`.scratch/rebuild-priorities/issues/20-mastering-to-done-19-restore-the-catalog-and-publish-person.md`.
Keep its checklist current; it remains incomplete.

The base is origin/main at `7615b3ee8`. PR #1242 (catalog coverage) and PR #1253
(portable data-catalog skill) are merged, verified through GitHub during handoff.
The old Codex worktree `catalog-quality-cases-20261030` still retains the original
uncommitted changes for recovery. This PR copies those changes onto a fresh base;
do not continue editing both copies. The shared main checkout's tracker edits,
visual artifacts and backup file are unrelated and were left untouched.

## Included work

`edgar_warehouse/rules/catalog.py` compares configured descriptions with one
HTML-unescape of native API descriptions, including column descriptions and
verification readback. Five invented positive/negative tests cover the comparison
helper. A new optional expected identity argument on `_upsert` is preserved WIP;
it is not yet used by a native quality publisher and needs review before merge.
The ticket records the operator's additional requirements and previous execution
claims. Those live catalog claims were not reverified during this handoff.

## Remaining implementation

1. Publish 18 configured contract checks and six Silver checks as named native
   quality cases, definitions only. Preserve five fixes as correction metadata
   and 43 profiling entries as proposals/evidence. These are inherited inventory
   counts: rediscover them from current configuration before claiming coverage.
2. Create domains and glossaries for each configured entity kind, terms for
   fields/identifiers/relationships and declared asset associations. Derive names
   and contextual meanings from configuration; preserve technical lineage keys.
3. Qualify an invented connected example through APIs: membership, identity,
   direction, drift rejection/repair, unchanged repeat, ownership and stale cleanup.
   Account for all created objects and reset only task-owned metadata in dependency
   order. Preserve unrelated curation and shared services.
4. Follow the data-catalog skill's operator review gate for the understandable
   example before expanding presentation. No source processing/provider requests,
   schedules, account changes or fabricated quality results are authorized here.
5. Complete affected tests, Standards/Spec/GoF review, final-head CI, and the
   parent ticket's publication/readback and Learning → skill items. The reusable
   skill now exists in merged #1253; assess remaining gaps before opening a
   separate skill change. Do not claim the parent ticket is complete.

## Review of the preserved diff

### Standards

Fresh Codex branch/worktree, API/CLI-only inspection, invented unit fixtures,
and no provider access or store writes. Live deployment evidence is inherited,
not requalified. Draft status retains unfinished validation and scope.

### Spec

The description correction is present. Named native quality cases, domains,
glossaries and configured business labels remain unimplemented. The five helper
tests alone do not prove server behavior or the complete publication/check path.

### GoF

The gof-refactor-reviewer skill is available and was used. Catalog history shows
successive lineage, profiling and coverage additions. Keep the existing pure
projection and callable transport boundary: no demonstrated present cost justifies
a class hierarchy. The optional identity override must retain exact ownership
checks when its future caller is added.

## Handoff checklist

- [x] Inspect live branches, worktrees, dirty state, main and merged PRs — 2026-10-30 18:28 ET; Git/gh inspection.
- [x] Preserve pending code, tests and ticket in a fresh worktree — 2026-10-30 18:28 ET; patch applied, overlap guard passed.
- [x] Record affected-test results and whitespace validation — 2026-10-30 18:29 ET; 29 catalog cases passed in 20.15 seconds with testmon, 95 genericity/guide-path checks passed in 0.43 seconds, git diff --check passed. Existing shared virtualenv reused without dependency installation.
- [x] Publish the draft PR and verify its remote head — 2026-10-30 18:30 ET; PR #1254 is OPEN/DRAFT with remote source head ef27b2c11ad553697de2ee98e884f37b27d6560d. This follow-up records the publication receipt; CI remains pending.
- [x] Learning → skill: none for this handoff — 2026-10-30 18:29 ET; parent catalog learning assessment remains open.
