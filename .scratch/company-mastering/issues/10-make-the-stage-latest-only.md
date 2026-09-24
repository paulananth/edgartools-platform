# Make the Stage latest-only, with bronze as the only history

Type: task
Status: open
Blocked by: none (design); build before the daily run feeds Clean MDM

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
- [ ] Settle what a decision cites once its assertion is replaced
- [ ] Settle how reversal and replay re-read bronze
- [ ] Settle field provenance after a replacement
- [ ] Migration on a populated store, Merge Stage change, PG16 tests
