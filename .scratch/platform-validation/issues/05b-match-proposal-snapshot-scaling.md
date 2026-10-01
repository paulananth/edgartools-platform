# The match proposal snapshot slows down as the store grows

Type: bug (found by the Person feed 1 Proving Run, 2026-10-01)
Status: open, not started. Code; needs a code session the operator allows.

## What was seen

The Person Proving Run sends batches of 1,000 readings, and each batch proposes
new Persons. Per batch:
- batch 40 took 74 s;
- batch 70 had not finished after more than 40 minutes;
- the test database ran at 150% CPU, inside `mdm.match_proposal_snapshot`.

Company's Proving Runs never showed it: ticket 27 applied only 6,726 records.

Reordered so every reading went first (no reviews yet), batches of 1,000 new
Persons still took about 5 minutes each with only about 7,000 rows stored.
A one-minute sample showed `match_proposal_snapshot` calls running 10–25 s and
`save_batch` calls 22–45 s, all growing with the store. At that rate, the
roughly 30,000 Persons of the capture need more than 3 hours.

## Why (from reading the function, `001_mdm.sql`)

`match_proposal_snapshot` hashes everything a proposal depends on. For each
call it scans, against the batch's keys:
- **every row of `mdm.source_reading`:** `body->>'subject' = ANY(keys) OR
  EXISTS(... relationships ...)`, and the `OR EXISTS` defeats any index;
- **every open review in `mdm.current_record`:** `body->'affected_subjects' ?|
  keys`, unindexed.

Every set-aside record opens a review. So the cost of one batch grows with
everything stored before it, and a full feed costs quadratic time.

## Workaround in the Proving Run

`proving_run.py` applies every reading first and every set-aside record after.
Production cannot choose that order. It was still too slow, so the Proving
Run now uses a seeded random cohort of 10,000 documents, as Company's CIK proof
did (ticket 05), plus a database-free pass of the rule over all 76,230.

## Checklist

- [ ] GoF consult on `match_proposal_snapshot` and `assessment.py`
- [ ] Profile `save_batch` for a 1,000-Person batch (`track_functions`)
- [ ] Make each branch an indexed lookup by key (subject, affected subjects,
  relationship targets), keeping the hash the same for the same state
- [ ] Measure: a 30,000-reading feed with 45,000 set-aside records, batch time
  flat
- [ ] Three-axis `/code-review`; PR; CI green; merge on the operator's word
