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

1. [x] **The latest-only Stage, written beside the history** (PR #715, merged
   `cadb99d3`, 2026-09-25 19:50 ET). Migration 038:
   `mdm_v2.stage_record`, key `(source_code, record_key)`, the winning
   reading, the resolved snapshot and its bronze reference. The evidence
   wrapper keeps it once the core has stored the batch, in the same
   transaction: the readings the batch newly stored, taken in (revision,
   mapping version) order, never the batch's hash order. A reading wins on a
   higher (revision, mapping version) and folds over the snapshot, so a
   sparse patch erases nothing it does not name; a duplicate, or an older
   reading delivered in a later batch, keeps the row; two readings at one
   (revision, mapping version) are refused. A batch may name each reading's
   bronze object (`occurrences`), set in the same step. Backfilled the same
   way on a populated store. PG16: when readings arrive in revision order,
   every Stage row equals what `current_claims` reads from the full history;
   where an older reading arrives later the two differ on purpose (15 tests).
   Limits recorded: a clash with an older reading the row already replaced
   goes unseen; a profile's identifying values must be text.
1b. [x] **GLEIF names its bronze objects; the channel for any source** (PR
   #716, merged `0df0be28`, 2026-09-25 20:17 ET). Native
   GLEIF batches name the verified member's `bronze_artifact_reference`, its
   raw evidence hash and `level1:record:<ordinal>`. A pinned source row may
   name its bronze object under `_origin.bronze`; the manifest reader turns
   it into that reading's occurrence, built field by field. PG16: every
   GLEIF Stage row in the four-company test names its archive; the SEC rows
   there carry fixture bronze to test the channel only.
1c. [x] **SEC names its bronze objects** (PR #717, merged `7d515861`,
   2026-09-25 21:04 ET). No production writer lands
   submissions rows in `sec_raw_object` (it holds filing artifacts only), but
   a Company row's `raw_object_id` **is** the sha256 of its submissions
   document. The warehouse capture path (`bootstrap_batch`, which produced the
   real local landing `local-fewco-20260917`) records each document's bronze
   path and sha256 in bookkeeping `pipeline_run.raw_writes_json`, keyed by the
   same run id the landing carries. `mdm bronze-receipts --run-id` writes
   those receipts (sha256 to object, one path per identical copy, canonical);
   `prepare-clean-company --bronze-receipts` requires the landing's own run
   and gives each row whose document they name `_origin.bronze` (object,
   sha256, locator `$`). Never a bronze listing per CIK. The
   acquisition-gated path (`drive-submissions-discovery`) records the same
   facts in the ledger's `source_revision`; a receipts builder for it waits
   for a landing from that path.
   Found in review (Claude, 2026-09-25): a run records every write, and
   filing attachments and ADV manifests carry no sha256, so receipts leave
   unhashed writes out; only a `succeeded` run's receipts are taken. Limits:
   - **SEC submissions are written with the mutable writer** (`write_bytes`,
     a date-partitioned key), not `write_immutable_bytes`, so a second fetch
     the same day replaces the object an earlier receipt names. The recorded
     hash still detects it: slice 4's bronze reread refuses a mismatch. A
     warehouse change for the operator to decide, not this slice: opened as
     [Write each SEC submissions document to bronze once](16-write-sec-submissions-bronze-once.md).
   - The Stage keeps bronze only for readings a batch newly stores, so
     re-preparing an already committed landing with receipts names bronze on
     no existing row; the approved path is a fresh rebuild from pinned input.
2. [ ] **Readers move to the Stage and compact decision receipts**, each with
   an old-versus-new parity test; the Stage's nullable `entity_id`, kept by
   the binding decisions. In three PRs (Claude, 2026-09-25 21:30 ET):
   - [ ] **2a. Who a record is bound to, and its winning reading.** Migration
     039: the Stage's `entity_id` (the bind decision's own entity, never its
     survivor: a binding never moves, `identity.replay`), set when a bind
     commits, refused if it names another entity, backfilled from
     `mdm_v2.decision`; and the winning reading's full body (`reading`),
     since the name rules read its provenance and slice 4 stops storing it
     elsewhere. Readers moved: `binding.holders`, the bound-subject lookup in
     `binding.propose`, `matching._stored`, `_bindings` and `_held_leis`.
     Survivors still resolve through `survivors()`. A latest reading is the
     highest (revision, mapping version) either way, so these readers match
     the old queries, held equal by PG16 tests on a seeded history that
     includes an older reading delivered later. Two intended differences,
     both where the history read could match a reading a later one replaced:
     `_stored` took the latest reading *that matched*, so a replaced Name
     Census LEI still matched; `_held_leis` counted every LEI any reading of
     a bound record carried. The Stage reads the current reading only, as
     `holders` already did. A GLEIF record's key is its LEI, so the second
     never differs on real GLEIF data.
   - [ ] **2b. The Merge Stage reads the Stage**: `load_closure`,
     `current_claims` and the assessment snapshot (028) read Stage
     snapshots, keeping the retired-source filter. `current_claims` leaves
     out a reading effective after the batch's as-of, and a folded snapshot
     cannot, so the refusal of future-effective readings recorded above for
     slice 4 moves here, at write time. Its test surface is measured first.
     An assessment still open when this ships goes stale and is re-assessed.
   - [ ] **2c. The views, provenance and compact receipts**: the per-kind
     Stage views (033/034) become latest-only; `consumer._provenance` reads
     the dated Company row and the compact receipt. Open design point: a
     field a sparse patch left in place was stated by an older reading, and
     the row keeps only the winner's bronze, so each claim item may need its
     own reading's bronze reference.
   Not covered by any slice yet: `mdm_v2.deferred_record` (read by
   `stage_waiting`, 036) also grows with every capture.
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
