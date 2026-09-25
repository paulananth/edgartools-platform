# Make the Stage latest-only, with bronze as the only history

Type: task
Status: claimed (Claude, branch `claude/company-mastering-10-latest-only-stage`, 2026-09-25 18:48 ET)
Blocked by: none

Build before the daily run feeds Clean MDM.

## Question

Operator, 2026-09-24 08:33 ET: the Stage must not hold history. It holds **only the latest
row per company per source**, upserted. **Bronze is the only history**: every
Stage row names the bronze object it came from, so any older version can be
re-read from S3 when needed.

Why: today a record's identity includes the capture it came from
(`publication_key` is hashed into `assertion_id`), and `mdm_v2.assertion` is
append-only (`immutable_row` trigger, migration 023). So every daily SEC
capture adds a row per company even when nothing changed, about 70,000 rows a
day from SEC alone. That grows without bound.

## What this reverses

- Ticket 01, amendment: "**assertions are never pruned**". Superseded.
- Ticket 03: the separate Stage history view. Dropped; bronze is the history.

## Consequences to design before building

Each must be settled, one at a time, before the migration is written:

- **Decisions cite assertion ids.** A `bind` decision names the assertion that
  justified it (`merge.py`, `identity.replay`); an upsert replaces that row.
  What does a decision cite once the row it named is gone?
- **Reversal and replay.** Undoing a wrong merge and replaying a past run read
  retained evidence today; they must re-read bronze instead.
- **Field provenance.** A master value names the source record that won; that
  record may since have been replaced by a newer version.
- **The immutable trigger** on the Stage table must go, while the evidence
  tables that stay append-only (decisions, batches) keep it.

## Checklist

- [x] Decide: latest-only Stage, upsert, bronze as the only history, each row
  naming its bronze object — operator (2026-09-24 08:33 ET)
- [x] Settle what a decision cites once its assertion is replaced —
  operator (2026-09-24 09:24 ET). The Merge Stage runs **at the end of each source load**, so
  a decision is always made on the version just loaded. It cites **the record**
  (source and key, e.g. `SEC / CIK 0000320193`, which never changes) and **the
  bronze object** it was made on. On the next load the merge re-checks the
  newer version: same identifiers, the match stands and the new fields open a
  new `mdm_v2.company` row (a name change alone never breaks a match, Q9);
  different identifiers, the match is not changed automatically and goes
  through the confidence bands (95% acts, below 50% to a Steward)
- [x] Settle how a wrong merge is corrected — operator (2026-09-24 09:29 ET): **fix the
  rules**. A wrong merge is a rule defect: the rule gets a new, tested version
  and the merge re-runs on the current Stage rows, which splits the wrong
  company (the combined `mdm_v2.company` row closes, one row per company
  opens, the merged-away ID returns from its alias, ADR 0013). **If the rules
  cannot fix it, quarantine** the records involved. Bronze is read only to show
  what the wrong decision saw; the correction never reloads old versions.
- [x] Settle what quarantine does — operator (2026-09-24 09:31 ET): quarantined records stay
  in the Stage, marked, and are **left out of matching** (no rule joins them
  automatically); each stays **its own company** in `mdm_v2.company` with a
  `quarantined` flag readers can see; only an **operator-approved rule
  change** lifts it
- [x] Settle the Stage key — operator (2026-09-24 17:19 ET): **key is (source, the
  source's own record number)**, e.g. (SEC, CIK 0000320193) or (GLEIF, LEI);
  every record has one from arrival. **The entity ID is a column on the same
  row**, filled by the MDM lookup when a matching rule finds or creates the
  Company, empty while the record waits. It is not in the key, because a
  waiting record has none. One row per company per source follows from the
  latest-only upsert.
- [x] Settle provenance after replacement — operator compact-receipt reply verified (2026-09-25 16:23 ET).
  keep raw history in bronze and only the latest normalized row in Stage.
  The immutable journal keeps compact decision receipts and bronze references,
  not full historical assertions. The dated Company row already retains each
  selected field's value, winner and conflicts; the receipt must carry the
  source key, exact bronze object/hash and locator, mapping and rule versions,
  decisive predicate values, and decision outcome. An old full raw record is
  re-read from verified bronze when investigation needs it.
- [ ] Migration on a populated store, Merge Stage change, PG16 tests: in the
  four slices below, each its own PR. Nothing stops being written, and nothing
  is deleted, until its replacement is proven on populated PostgreSQL 16.

## Slices (Claude, 2026-09-25 18:48 ET)

Found while planning (facts, not rulings):
- SEC Company records cite the silver landing member by hash, not bronze.
  The same capture lands `sec_raw_object` (CIK, `storage_path`, `sha256`), so
  the SEC adapter can carry each record's bronze object and hash. GLEIF
  records already carry the Golden Copy archive hash and the record ordinal.
- No current source sends a record effective after its load: SEC records
  carry no effective time; a GLEIF record's is its `LastUpdateDate`, which
  precedes its publication. **Technical decision (Claude):** once the Stage
  is the authority (slice 4), it refuses a record effective after its
  batch's as-of, rather than hold a value not yet in force. Until then it
  keeps the winning reading whatever its effective time, since unit tests of
  field selection still use future-effective readings. Reversible if a
  future source needs it.
- GLEIF records deliberately leave delivery details (archive hash, record
  position) out of the assertion, so one record read from two deliveries is
  one assertion (`adapters.py`). So the bronze reference cannot live in the
  assertion: a batch names each reading's bronze object beside it
  (`occurrences`), and the Stage keeps the winning reading's.
- Undoing a binding replays decisions (`identity.py`: reverse, revoke), so
  the Stage's `entity_id` belongs with the binding readers in slice 2.
- Readers of the full history today: `merge.load_closure`,
  `binding.holders`, `matching._stored`/`_held_leis`,
  `survivorship.current_claims`, `consumer._provenance`, the per-kind Stage
  views (033/034), `stage_waiting` (036), the dated Company trigger (037),
  assessment (028/035); `consumer.py` also reads historic objects from
  `batch.effects`, and the journal publication carries the full request.

1. [ ] **The latest-only Stage, written beside the history.** Migration 038:
   `mdm_v2.stage_record`, key `(source_code, record_key)`, the winning
   reading, the resolved snapshot and its bronze reference; kept by a trigger
   on the assertion write in the same transaction (037's pattern) and
   backfilled in arrival order on a populated store. A reading wins on a
   higher (revision, mapping version); a duplicate or a late older delivery
   keeps the row; two readings at one (revision, mapping version) are
   refused. Each winner folds over the previous snapshot, so a sparse patch
   erases nothing it does not name. A batch may name each reading's bronze
   object (`occurrences`). PG16: every Stage row equals what
   `current_claims` reads from the full history (12 tests).
1b. [ ] **The sources name their bronze objects.** The SEC bundle pins
   `sec_raw_object` and names each CIK's submissions object and hash; the
   GLEIF bundle names the Golden Copy archive and the record's ordinal; the
   apply command passes them as `occurrences`.
2. [ ] **Readers move to the Stage and compact decision receipts**, each with
   an old-versus-new parity test; the Stage's nullable `entity_id`, kept by
   the binding decisions.
3. [ ] **Compact `batch.effects`**: a request hash, compact receipts and a
   fenced duplicate-observation capability; existing batches migrated
   additively, never rewritten or truncated.
4. [ ] **Stop the growth**: stop appending full assertions; lift the
   append-only guard on the Stage only; merge at the end of each source load;
   a missing or mismatched bronze object on reread is a blocking error.

## Implementation contract for the next change

- Add a unique Stage key `(source_code, record_key)`, with a nullable bound
  `entity_id`. A later source revision replaces that row only if its native
  revision and mapping reading win the declared order; duplicates and late
  older deliveries keep the current row. Every row carries an exact bronze
  object and hash. No source record is silently retired by absence.
- A patch source's latest Stage row must include the **resolved current source
  snapshot** as well as the latest raw assertion. Apply value, clear, retract
  and unknown operations against the previous snapshot atomically, so a sparse
  patch cannot erase an unchanged field when old Stage rows leave. Preserve
  each surviving field's source assertion and publication references.
- A bound record is reassessed at the end of its source-load batch. Same
  identifiers keep its ID; a contradiction routes to correction/review, never
  moves a binding by overwriting the Stage row. Merge/reversal replays current
  Stage snapshots; bronze is read only to investigate a past decision.
- Stop copying full assertions into `batch.effects`. Keep a request hash and
  compact receipts so a redelivery can be checked and observed without
  recomputing a hash from a retained full request. This requires a fenced
  duplicate-observation capability and a migration of existing batches before
  changing `commit_batch`; do not truncate prior audit data in place.
- The Company API obtains historic winner evidence from dated Company rows and
  the compact receipt. A verified bronze reread supplies the full source row
  on demand. A missing or hash-mismatched bronze object is a blocking recovery
  error, not a fabricated provenance response.
- Prove old and new layouts on populated PostgreSQL 16, including sparse
  patches, reordered/future-effective revisions, correction, reversal, lost
  acknowledgements and publication retries before the migration is enabled.
