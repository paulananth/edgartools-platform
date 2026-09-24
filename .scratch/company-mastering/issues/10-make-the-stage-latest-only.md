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
- [ ] Settle what quarantine does to the records and to `mdm_v2.company`
- [ ] Settle field provenance after a replacement
- [ ] Migration on a populated store, Merge Stage change, PG16 tests
