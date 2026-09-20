# Write and evidence the per-family checkpoint-key proposal

Type: task
Status: resolved
Blocked by: none

## Question

Write the proposal for Codex/Grok: why `mdm_v2.checkpoint` needs a
per-family key, evidenced from their own files, with a concrete shape and
the questions that remain theirs.

## Answer

### What exists today

`edgar_warehouse/mdm/migrations/023_clean_mdm.sql` (on
`origin/codex/clean-mdm-integration`):

```sql
CREATE TABLE mdm_v2.checkpoint (
    consumer text PRIMARY KEY,
    position bigint NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id)
);
```

Written only by `commit_batch_core`, which checks and advances it:

```sql
SELECT coalesce((SELECT position FROM mdm_v2.checkpoint WHERE consumer=r->>'consumer'),0) INTO pos;
IF (r->>'expected_checkpoint')::bigint IS DISTINCT FROM pos
   OR (r->>'checkpoint')::bigint IS NULL OR (r->>'checkpoint')::bigint <= pos THEN
    RAISE EXCEPTION 'Stale or nonadvancing checkpoint';
END IF;
...
INSERT INTO mdm_v2.checkpoint VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id')
ON CONFLICT(consumer) DO UPDATE SET position=excluded.position,batch_id=excluded.batch_id;
```

One consumer, one scalar position. The fencing (expected == stored, new >
stored) is exactly right and should be kept; only the key is too narrow.

### What the shared foundation needs

From [MDM Enrichment Shared Foundation](../../mdm-enrichment-shared-foundation/map.md):

- [Ticket 02](../../mdm-enrichment-shared-foundation/issues/02-decide-gleif-publication-family-taxonomy.md):
  GLEIF alone is ~8 independently checkpointed publication families — one
  Golden Copy family (Level 1 + RR + REPEX together) plus one family per
  identifier mapping (ISIN daily, OpenCorporates bi-weekly, BIC/MIC/QCC/GEM
  monthly, CIQ deferred). Each has its own cadence and its own checkpoint.
- [Ticket 03](../../mdm-enrichment-shared-foundation/issues/03-decide-delta-continuity-and-recovery-order.md):
  a family that fails continuity is reconciled from a full Golden Copy
  **for that family only** — "never advancing a sibling family's
  checkpoint."
- [Ticket 06](../../mdm-enrichment-shared-foundation/issues/06-define-consumer-checkpoint-transaction-boundary.md):
  the checkpoint row must record **which publication** the consumer
  consumed — `(source_family, source_native_revision)` — inside the same
  `commit_batch` transaction, so the commit says what it advanced past.

A single `position bigint` per consumer cannot hold "Company consumer is at
Golden Copy 2026-09-19 but ISIN mapping 2026-09-18," and the GoF review's
Appendix C item 3 asked for `(consumer, source_family, publication_family)`
plus committed publication and continuity proof for exactly this reason.

### Evidence this is your direction already, not a change of direction

1. `docs/specs/clean-mdm/recovery.md` line 20 — your own owner table:
   *"Consumer Checkpoint | Committed bounded progress for one consumer,
   contract/policy version, **family/epoch and source position**."* The
   spec already describes a family-bearing checkpoint; the 023 DDL lags it.
2. `docs/specs/clean-mdm/source-evidence.md`, "GLEIF and mapping extension
   boundary": *"Each of the six mappings has its own publication, cadence,
   checkpoint and recovery. A consumer may require several families, and
   advances only when all of its prerequisites are verified."* Same
   requirement, in your words.
3. `edgar_warehouse/mdm/clean/company_source.py` lines 195–199 — your first
   bounded adapter already works around the narrow key by minting a fresh
   consumer string per batch:
   ```python
   "consumer": f"{SOURCE_CODE}/{digest([publication_key, revision, payload_hash, as_of])}",
   "expected_checkpoint": 0,
   "checkpoint": 1,
   ```
   Every batch is its own consumer at position 0→1. That keeps the fence
   honest but makes `mdm_v2.checkpoint` a batch log rather than a
   checkpoint: nothing in the table answers "where is the Company consumer
   on SEC company evidence?" without parsing consumer strings.

### Proposed shape

Keep the fence; widen the key; add what the row must say.

```sql
CREATE TABLE mdm_v2.checkpoint (
    consumer            text   NOT NULL,   -- e.g. 'company'
    source_family       text   NOT NULL,   -- change_ledger.source_family, e.g. 'gleif'
    publication_family  text   NOT NULL,   -- e.g. 'golden_copy', 'isin_lei'
    position            bigint NOT NULL,   -- unchanged fence semantics
    committed_publication text NOT NULL,   -- change_ledger source_native_revision consumed
    continuity_proof    jsonb  NOT NULL,   -- per-family fields declared in
                                           -- change_ledger.source_registry_coverage
    batch_id            text   NOT NULL REFERENCES mdm_v2.batch(batch_id),
    PRIMARY KEY (consumer, source_family, publication_family)
);
```

`commit_batch` request gains `source_family`, `publication_family`,
`committed_publication`, `continuity_proof`; the existing
`expected_checkpoint`/`checkpoint` fence applies per key instead of per
consumer. `company_source.py`'s per-batch consumer string becomes
`consumer='company', source_family='sec', publication_family='company_landing'`
with a real advancing position.

No new table, no new function — one widened key and three columns on a
table you already own, on a function you already own.

### Constraints this proposal respects

- Still one atomic `commit_batch`; the checkpoint still advances only with
  the accepted evidence (your "Transaction boundary" section, verbatim).
- Still fenced: stale `expected_checkpoint` per key rejects, same as now.
- Immutable history untouched — `checkpoint` is already a mutable
  projection in your design (it is not in the `immutable_row` trigger
  list), so widening it changes no append-only guarantee.
- Q1–Q16 policy untouched.

### Open questions — yours, not decided here

1. Whether `committed_publication` should FK anywhere. The foundation
   decided a publication is *derived* from `change_ledger.source_revision`
   rows (no publication table), and `change_ledger` is a separate database,
   so a FK is impossible; a text identity is what's proposed. If you prefer
   a local `mdm_v2.dataset`-level publication row instead, that is your
   call.
2. Whether `continuity_proof` lives on the checkpoint row (proposed) or on
   `mdm_v2.batch.effects`, with the checkpoint row pointing at the batch.
3. Migration path for existing rows written under the per-batch consumer
   string workaround.
4. Whether a consumer that requires several families ("advances only when
   all of its prerequisites are verified") is enforced in `commit_batch`
   or in the adapter.
