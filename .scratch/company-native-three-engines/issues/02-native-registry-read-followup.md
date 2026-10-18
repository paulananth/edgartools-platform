# Native registry consumption follow-up

Status: read repair and PR publication complete; latest-head CI pending.

PR #1096 merged the earlier adapter checkpoint as `d16ff817`. The operator
requested a new PR for the remaining read fix. This branch starts at that
current main, in its own worktree. Full Company activation stays incomplete
in [ticket 01](01-complete-native-activation.md).

## Checklist

- [x] Reproduce the actual native Merge Stage policy read failure on MySQL: its fixed `mdm.policy` query selects the wrong database; retain the private failure evidence — 2026-10-18 19:49 ET.
- [x] Delegate typed policy and original dataset-contract retrieval to the existing skill adapter, using the caller's transaction; preserve shared policy validation, missing-policy outcomes and current/frozen mapping semantics — 2026-10-18 19:49 ET.
- [x] Verify the same actual native policy consumer and exact-source contract reads on PostgreSQL (2.11 s), MySQL (2.20 s), SQL Server (3.48 s), including long Unicode, case/accent distinctions, missing keys and original-versus-revised mappings — 2026-10-18 19:49 ET.
- [x] Run affected merge, identifier binding, matching, unchanged/deferred batch, execution, frozen-run and skill checks in this new worktree: 192 passed, one pre-existing strict expected failure (33.11 s). The expected failure concerns synthetic identifier changes under the existing rule; it was not added or weakened here — 2026-10-18 19:49 ET.
- [x] Review Standards, Spec and GoF independently; no open findings. The reviewed implementation matches the new worktree byte for byte. Build and isolate both package forms, resolving the canonical adapter and all three runtime resource pins — 2026-10-18 19:49 ET.
- [x] Publish [PR #1097](https://github.com/paulananth/edgartools-platform/pull/1097) from `codex/mdm-native-registry-reads-20261018`; verify it is open and ready for review with only the seven follow-up files. The tested code commit is `7afdd791`; latest-head CI remains separate from the merged checkpoint's nine passing checks — 2026-10-18 19:50 ET.
- [x] Learning → skill: `skills/mdm-engineering/references/storage-adapters.md`, Native registry integration, now requires typed consumption in the selected database and distinguishes original contracts from versioned mappings — 2026-10-18 19:49 ET.

## Review

### Standards

Storage queries stay in the skill-owned adapter. No runtime module, provider
request, source/entity branch or native Store bypass is added. Reads use the
existing connection and bound exact keys. The three-engine proof uses isolated
temporary databases and invented fixtures.

### Spec

The existing common Merge Stage and execution path consume the selected
engine's typed registry content. Dataset lookups preserve the append-only
contract body; they do not substitute the latest mapping or change approval.
The native Store, run control and full source activation are not qualified by
this read fix.

### GoF

Relevant history and the current diff support retaining the existing Adapter
boundary and plain functions. The repair removes repeated fixed-schema reads;
another hierarchy, algorithm or pipeline is not justified.
