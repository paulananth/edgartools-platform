# The match proposal snapshot slows down as the store grows

Type: bug (found by the Person feed 1 Proving Run, 2026-10-01)
Status: parts 1 (#772) and 2 (#774) merged; the Person timing run and finding 5 remain, deferred.

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

## Operator rulings (2026-10-01)

- 21:16 ET: "yes" to 05b doing the database fixes after 06a2 merges (indexes,
  and reviews no longer copying the whole save's subjects and entities).
- About 21:26 ET: "Fix reviews first (Recommended)": the review fix goes ahead of
  06a2's merge, because 06a2's test run failed twice on it.

## Part 1: each review names only its own records

**Seen (06a2 test run, 2026-10-01):** a save of 200 GLEIF links came to 24 MB,
and after links existed a save of 200 ordinary GLEIF records came to 19 MB.
Both are over the 16 MiB cap in `write_batch`.

**Why:** every open review carries `affected_subjects` (every record in the
save's closure) and `affected_entities` (every Company in it). So a save's
size grows with reviews × closure, and links make closures bigger.

**Why it is safe to keep only the review's own records:** the closure is a
connected component. A reading links both ways (subject and either link end),
and a decision's anchors are exactly the fields the decision query matches
(`anchors`, `merge.py:25`). So a later save that touches any record of the
component loads all of it, and the retirement query (`merge.py`, by
`entity_id`, `subject` or `affected_subjects`) finds the review by its own
records. The match proposal snapshot uses the same closure keys
(`merge.py` preview scope), so it still sees the review.

**Each review's own records:** its `subject`; the members of its `entity_id`;
the members of the Companies its `edges` join (conflicting parents, cycles);
for `ambiguous_override_owner`, the members of the override's Company. Each
Company is its current one, never an alias. A review that names no record
(an ownerless override whose Company has lost its records) falls back to
every record of its closure, as before: refusing it would block every later
save of that family (Spec review, 2026-10-01).

**GoF consult (21:30 ET):** `merge.py` has 13 commits and this block changed
with 06a; the change is one named helper that says which records a review is
about. No pattern; leave the rest.

## Checklist

- [x] GoF consult (above; 21:30 ET 2026-10-01)
- [x] Measure what fills a save (06a2 run with a per-part size line, 21:37 ET 2026-10-01): SEC saves 6.2 MB with reviews under 0.1 MB; the second GLEIF save 3.89 MB, of which reviews 1.36 MB and their copied lists 1.34 MB
- [x] Failing tests: `tests/integration/test_clean_review_scope.py`, 3 tests (a
  review in a 21-Company family names only its record; a parent conflict names
  its three Companies and is retired by a save through a sibling; an override
  with no record names its Company's records and is retired on revoke). Two
  failed on the old engine (21:32 ET); all pass on the fix (21:33 ET). The
  snapshot already sees reviews by the same closure keys (`merge.py` preview
  scope); `test_clean_mdm_postgres` covers staleness and passes
- [x] Code: `merge.review_scope`; link conflict and cycle reviews name their Companies (`relationships.py`); current Companies, never aliases; a review with no record falls back to its closure (`tests/mdm/test_clean_review_scope.py`, 4 tests; 21:41 ET 2026-10-01)
- [x] MDM, unit and architecture suites; named integration files (after the review fixes, 21:43–21:46 ET 2026-10-01: MDM+unit 884, architecture 249, test_clean_mdm_postgres 46, review_scope 3+4, relationship_identity 5; before them, 21:37 ET: identifier_binding 24, change_journal_source_evidence 30, company_one_place 6, stage_binding 7, shared_cik 3)
- [x] 06a2 test run on this fix, with 200-record saves for links and GLEIF (2026-10-01 21:51–22:07 ET: passed; largest save 6.3 MB; links 2.4 and 1.2 MB)
- [x] Three-axis `/code-review` (21:41 ET 2026-10-01). Standards: override lookup only for
  `ambiguous_override_owner`; no name reuse; no side-effect on `groups`; fixed.
  GoF: leave it; a comment where link reviews are built. Spec: no blocker;
  current Companies, not aliases, and a fallback instead of a refusal; fixed,
  with `tests/mdm/test_clean_review_scope.py`. Noted: link conflict and cycle
  reviews get new ids once (they now name `entities`); the old ones are
  retired by the next save of their family.
- [x] PR #772; CI green; merged on the operator's "merge" (2026-10-01 21:50 ET)
- [ ] Open for slice 6: the closure follows links, so a save loads the whole
  corporate family; at full GLEIF scale a family may reach the closure limit
  or the byte cap. Whether link ends should stop the closure is a design
  question.

## Part 2: indexes (after part 1)

Operator: "agreed" (2026-10-01 about 22:23 ET) to doing 05b part 2 next.

**GoF consult (2026-10-01 22:25 ET):** the closure query in `merge.py` and the
snapshot in SQL changed together in 06a and change together again here. The
cheap answer is one indexed function for "the records a reading's links name"
(`mdm.reading_link_subjects`), used by the index, the snapshot and the
closure alike. No pattern; leave the rest.

**Finding 2's gate is met:** after #772 a review names only its own records;
the 06a2 run measured review lists at about 0.01 MB per save, so a review adds
a few GIN entries, not about 1,000.

- [x] Migration 003: findings 1 (link-subject GIN on `source_reading`), 2
  (`current_record` relationship and review lookups), 3 (`master_entity` id as
  text), 4 (`decision` retire-source); the snapshot and the closure use them
  (`003_lookup_indexes.sql`; 2026-10-01 22:30 ET)
- [x] Test: with sequential scans off, the snapshot, the closure and the
  retirement query read no table in full (`pg_stat_user_tables.seq_scan`), and
  each of the 8 indexes is used (`pg_stat_user_indexes.idx_scan`), on a store
  with 300 open reviews, analyzed (`test_clean_lookup_indexes.py`; 2026-10-01
  22:33 ET). Dropping an index makes it fail (checked for 4). With 3 reviews
  PostgreSQL read every review through another index, which is why the store
  holds 300
- [x] Test: a populated store at 002 takes 003 and gives the same snapshot
  hashes (4 scopes) and keeps its rows; the closure finds the same readings
  and decisions as the old query (2026-10-01 22:33 ET). Affected files and
  suites passed (22:32–22:37 ET); from here on, locally only the affected
  files (operator, 22:36 ET: "it takes too long for every test")
- [ ] ~~Company run (06a2 script): SEC part, GLEIF save and total times against
  try 3~~ deferred to the next Person run: 16 minutes, and the operator asked
  for shorter test cycles (22:36 ET); the index-use test is the evidence for
  this PR, timings come from the next Person feed run
- [ ] ~~Finding 5 (`cascade_lei` on `stage_record`)~~ deferred: only once scan
  counts show `stage_record` read in full on Company runs
- [ ] ~~The snapshot is computed three times per batch~~ out of scope: a code
  shape change, not tuning

- [x] GoF consult on `match_proposal_snapshot` and `assessment.py` (Part 2 note above, 2026-10-01 22:25 ET)
- [ ] ~~Profile `save_batch` for a 1,000-Person batch (`track_functions`)~~ deferred to the next Person run, with its timings
- [x] Make each branch an indexed lookup by key (subject, affected subjects,
  relationship targets), keeping the hash the same for the same state
  (migration 003 and its tests, above)
- [ ] ~~Measure: a 30,000-reading feed with 45,000 set-aside records, batch time
  flat~~ deferred to the next Person run (operator, 22:36 ET: shorter test
  cycles). The tests prove an index serves every lookup; they do not prove
  PostgreSQL picks it at default settings, which only a real run shows
- [x] Three-axis `/code-review` (2026-10-01 22:42 ET). GoF: leave it; a test
  that SQL and Python agree on a reading's links (added; the SQL now ignores an
  empty name, as Python does). Standards: comments on the role setting and the
  runtime functions (added). Spec: no blocker; the full-read test waits for the
  counts to settle and the closure test compares entities too (added); the
  index use is proven possible, not chosen at default settings (Person run).
  Index file 4 passed, core MDM and schema comments 51, MDM+unit 884
  (22:39–22:43 ET)
- [x] PR #774; CI green; merged on the operator's "yes" (2026-10-01 22:47 ET)
