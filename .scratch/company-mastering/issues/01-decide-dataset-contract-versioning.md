# Decide how a Dataset Contract version changes without re-binding every record

Type: grilling
Status: resolved 2026-09-22
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

## Answer

Operator decisions, 2026-09-22, one question at a time. A mapping version is
a number the platform owns. It is **not** `schema_version`, which describes
the source's own schema and is pinned by the dataset today
(`023_clean_mdm.sql:160`).

### The five decisions

1. **A re-read keeps both rows** (Q1a). Registering a new mapping version
   never rewrites an assertion. The old row stays exactly as it was, and the
   new reading sits beside it. `source_code` never changes, so no Company is
   re-bound and no subject moves (`subject_key(source_code, record_key)`).
2. **Two rows, current and one backup** (operator). Per
   `(source_code, record_key, publication_key)` the store keeps the current
   mapping version and the one before it. Older ones are pruned.
3. **Except where a decision still cites it** (Q2a). A row that a live
   decision or selected field points at is kept and marked superseded, and is
   pruned only once nothing cites it. Without this, a Company could hold a
   value whose reason no longer exists: `consumer.py:31` reads the winning
   assertion by id.
4. **Registration alone re-reads nothing** (Q3a). A new version applies to
   publications read from then on. Re-reading an already consumed publication
   is a separate, explicit, bounded request, and that request is what creates
   the second row. One source may therefore hold two mapping versions for a
   while; every row says which one produced it.
5. **Identity parts may never change within one `source_code`** (Q4a):
   `record_key`, `publication_key`, and the adapter's `record_key`,
   `record_key_format`, `identifiers` and `identifier_formats`. The engine
   compares these itself, so the protection never rests on how an author
   labels a change. Everything else — a new field, a corrected read, a
   renamed output — is a new mapping version. Changing an identity part means
   a different dataset, and that is the one case where a new `source_code` is
   right.
6. **The version is a column, not part of the hashed body** (Q5a). An
   assertion id is `digest(body)` (`evidence.py:90`); putting the version
   inside the body would change every existing id and orphan every stored
   decision. Existing rows are stamped version 1, and the column is required,
   so no row has an unknown mapping version.

### The migration design (031)

- `ALTER TABLE mdm_v2.assertion ADD COLUMN mapping_version bigint NOT NULL
  DEFAULT 1 CHECK (mapping_version >= 1)`, and a `superseded_at timestamptz`
  for rows kept only because a decision cites them. Existing rows take the
  default, so no id changes and no reference breaks.
- Replace `UNIQUE(source_code, record_key, publication_key)` with
  `UNIQUE(source_code, record_key, publication_key, mapping_version)`. This is
  what lets a second reading exist at all; today it raises a unique violation,
  because `apply`'s `ON CONFLICT(assertion_id) DO NOTHING` does not cover it.
- A new `mdm_v2.dataset_mapping(source_code, mapping_version, body,
  registry_version, registered_at)`, with the body immutable per
  `(source_code, mapping_version)`. `mdm_v2.dataset` keeps one row per
  `source_code` and points at the current mapping version, so every existing
  reader and the registry-authority checks keep working unchanged.
- `register_dataset` gains one path: same `source_code`, changed body →
  compare the protected parts; refuse on any difference, otherwise insert the
  next `mapping_version` and move the pointer. An identical body is still the
  no-op it is today.
- `apply`'s schema check reads the mapping version's body rather than only the
  current one, so a batch produced by the backup version is still accepted
  while it exists.
- Survivorship orders by `mapping_version` after `revision` and
  `publication_key` (`survivorship.py:41`), so the newest reading of one
  record wins without changing how different revisions compete.
- Pruning is a bounded, explicit operation, never a side effect of a write:
  for each `(source_code, record_key, publication_key)` keep the two highest
  mapping versions, and delete lower ones only where no decision and no
  selected field cites the assertion id.

### What this does not do

It does not re-project anything, activate any rule, or change how a Company is
chosen. It is the lifecycle that lets a mapping be corrected at all. The
limit it accepts: replay reaches the current and the previous mapping version
only. An older reading can be rebuilt from the retained raw artifact, but it
is not kept in the store.
