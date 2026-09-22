# Decide how a Dataset Contract version changes without re-binding every record

Type: grilling
Status: open
Blocked by: none

## Question

Codex's named gate, accepted as blocking request 4: "Preserve stable
`source_code`/source subjects while pinning the exact immutable mapping
version on assertions and replay. A new source code per edit is not an
acceptable lifecycle."

Today a dataset body is immutable per `source_code` (`store.py:217-224`), and
every assertion is keyed by `(source_code, record_key, publication_key)`
(`023_clean_mdm.sql:50`). So a mapping change has one path: a new
`source_code`, which re-binds every record of that source and breaks its
history.

Decide:
1. **Where the mapping version lives** — a column on the assertion, a field in
   its body, or a separate registered mapping row the assertion points at.
2. **What stays stable** — `source_code` and the record's subject identity
   must not move because mapping code changed.
3. **What a version bump re-projects** — every record, only the fields whose
   mapping changed, or nothing until a replay is asked for. The Merge Stage's
   bounded-rebuild contract sets the ceiling.
4. **What a registration checks** — which changes are compatible (a new
   optional field) and which are not (a changed record key).
5. **The migration** — how existing assertions gain a version without a
   rewrite, and what an un-versioned row means.

Answer as a decision plus a migration design, not code. The next ticket
depends on it, and so does every later projection claim.

## Inputs

[Codex response](../../handover/2026-09-22-codex-source-contract-response.md),
[source evidence contract](../../../docs/specs/clean-mdm/source-evidence.md),
[merge stage](../../../docs/specs/clean-mdm/merge-stage.md),
[policy language §11 change and replay](../../../docs/specs/mdm/policy-language.md),
research 01 on the Source Contract map (the immutability finding).
