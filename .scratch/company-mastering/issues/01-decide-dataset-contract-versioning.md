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

> **Amended 2026-09-22** after [the challenge pass](../research/01-02-challenge.md)
> checked these decisions against the runtime. Decision 6 is **reversed** and a
> seventh is added; see "Amendments" below. Decisions 1-5 stand, except that
> decision 1 only becomes true once the amendment lands, and decisions 2 and 3
> are still open. Read the amendments before the migration design.

### The six decisions

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

### Amendments (operator, 2026-09-22)

The challenge pass found that decision 1 — a re-read keeps both rows — is not
something the runtime permits today, in either of the only two cases. A re-read
whose reading **changed** raises `Conflict("Source native revision has
contradictory publications")`, because survivorship groups by subject, which a
re-read does not move, and then refuses two assertions that share a `revision`
(`survivorship.py:43-44`). A re-read whose reading did **not** change produces
the same `assertion_id` and is silently dropped by `ON CONFLICT(assertion_id)
DO NOTHING` (`023_clean_mdm.sql:168`). Two amendments make decision 1 true.

7. **The mapping version is part of the assertion's identity** (operator,
   reversing decision 6). It goes in `body`, so the fingerprint covers it, and
   is lifted into a `bigint` column beside `body` for indexing — the same
   pattern `source_code`, `record_key`, `publication_key`, `revision` and
   `effective_at` already follow (`023_clean_mdm.sql:41-51`). A plain counting
   number, 1, 2, 3; never a hash.

   Decision 6's reason was that putting the version in the body would change
   every existing id. It would not: existing bodies are never rewritten and are
   never re-validated, because `validate_assertion` runs on incoming assertions
   only (`merge.py:238`). A stored body with no `mapping_version` key **means
   version 1**, which is the same thing the column's `DEFAULT 1` says. No id
   moves and no stored decision is orphaned.

   The reason to reverse it: outside the fingerprint, two readings of one
   publication produce the *same* `assertion_id`, so the second is thrown away
   on insert and decision 1 cannot hold. Two rows a fingerprint cannot tell
   apart are not two rows. It also keeps evidence self-describing —
   `consumer.py:30` hands back `a.body` as the reason behind a selected field,
   and that body should say which reading produced it.

   **As implemented**, a first reading omits the key rather than stating 1:
   absent and 1 describe the same reading, so version 1 has one canonical form.
   That keeps this amendment's promise literally — no assertion id moves, for
   rows already written *and* for first readings written from now on, which the
   amendment did not contemplate. The pinned representative fixture passing
   unchanged is the evidence. It gives up half of the self-describing reason
   above: a version-1 body does not say so. The lifted column always states the
   reading, and only a re-read carries the key in its body.

8. **The revision guard's key widens to `(revision, mapping_version)`**
   (operator, `survivorship.py:43-44`). The guard exists to catch one real
   defect: a source that published two contradictory things under one native
   revision. A second reading of one publication is not that defect, and today
   the guard cannot tell them apart. Widened, it still raises on two
   contradictory bodies at the same revision *and* mapping version, and stops
   mistaking a re-read for a lying source. No loader change is needed, because
   `merge.py:50-53` selects `body` and the version is now in it.

   The alternative considered and rejected: collapse to the newest reading
   before survivorship walks. Equal cost, but it splits one check across two
   places and leaves the guard's wording intact rather than its job.

Consequences these two carry, which the migration must also cover:

- `assertion()` gains `mapping_version` in the body it builds, and
  `validate_assertion`'s closed key list gains it too (`evidence.py:60-113`).
  Absent means 1, for stored rows only; an incoming assertion states it.
- `apply` stops inserting the batch item verbatim: the lifted column is written
  from the body's value (`023_clean_mdm.sql:166-167`).
- Survivorship's ordering by `mapping_version` (in the migration design below)
  now reads it from the body rather than needing a column in the query.

9. **Assertions are never pruned** (operator, replacing decisions 2 and 3).
   Nothing in Clean MDM is deleted: batches, assertions and decisions are all
   append-only and generations only count upward (`023_clean_mdm.sql:25`,
   `:138-150`). "Two rows, current and one backup" would have been the first
   delete path this store has ever had, and it was unreachable anyway — there
   is no foreign key to the assertion table, but every retained batch's effects
   cite assertion ids and `consumer.py:36-37` raises on a missing one, so
   "pruned only once nothing cites it" almost never releases a row. Decisions 2
   and 3 could not both hold.

   The prune was bounding something decision 4 already bounds: registering a
   version re-reads nothing by itself, so a second row appears only when an
   operator explicitly asks for a bounded re-read. Dropping the prune removes
   the conflict rather than arbitrating it, and costs nothing today, because no
   measurement says assertion storage is a problem.

   If it ever becomes one, the honest fix is to bound how far back a generation
   can be read and let assertions follow, decided then with numbers. Retention
   is therefore **not specified** here, rather than specified as none forever.

### The migration design (031)

- `ALTER TABLE mdm_v2.assertion ADD COLUMN mapping_version bigint NOT NULL
  DEFAULT 1 CHECK (mapping_version >= 1)`. Existing rows take the default, so
  no id changes and no reference breaks. (The `superseded_at timestamptz` this
  bullet first carried is struck by amendment 9: no row is ever kept *only*
  because something cites it, because no row is ever dropped.)
- Replace `UNIQUE(source_code, record_key, publication_key)` with
  `UNIQUE(source_code, record_key, publication_key, mapping_version)`. This is
  what lets a second reading exist at all; today it raises a unique violation,
  because `apply`'s `ON CONFLICT(assertion_id) DO NOTHING` does not cover it.
- A new `mdm_v2.dataset_mapping(source_code, mapping_version, body,
  registry_version, registered_at)`, with the body immutable per
  `(source_code, mapping_version)`. ~~`mdm_v2.dataset` keeps one row per
  `source_code` and points at the current mapping version~~ — **struck when
  implemented.** `mdm_v2.dataset` carries the append-only trigger installed by
  migration 023 (`023_clean_mdm.sql:101-103`), so a mutable "current" column on
  it could never be updated. The current reading is the **highest
  `dataset_mapping` row**, derived, never stored.

  The consequence, which the original wording hid: "every existing reader keeps
  working unchanged" was true only because every existing reader would then have
  read reading 1's body forever. A corrected mapping would have been written and
  never used. Both adapter entry points now resolve the reading and its body
  together through one accessor (`store.current_reading`), and thread the
  reading into the assertion.
- `register_dataset` gains one path: same `source_code`, changed body →
  compare the protected parts; refuse on any difference, otherwise insert the
  next `mapping_version` and move the pointer. An identical body is still the
  no-op it is today.
- `apply`'s schema check reads the mapping version's body rather than only the
  current one, so a batch produced by any registered version is still accepted.
- Survivorship orders by `mapping_version` after `revision` and
  `publication_key` (`survivorship.py:41`), so the newest reading of one
  record wins without changing how different revisions compete.
- ~~Pruning is a bounded, explicit operation~~ — **struck by amendment 9.**
  Migration 031 adds no delete path and no `superseded_at`: every reading is
  kept, and the store stays append-only.

### What this does not do

It does not re-project anything, activate any rule, or change how a Company is
chosen. It is the lifecycle that lets a mapping be corrected at all.

(The limit this section first accepted — replay reaches the current and the
previous mapping version only — is struck by amendment 9. Replay reaches every
reading, because every reading is kept.)
