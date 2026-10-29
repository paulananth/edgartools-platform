# 147: A consumer page carries each master's whole saved batch request

Priority: 147. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 14:20 ET.

Type: bug. Status: resolved (2026-10-29 07:43 ET). Found by ticket 146.

## Found (2026-10-28, `company-on` after its conversion, counts only)

`ContractReader.snapshot_page` (and `page`) reads masters through the storage
adapter's `read_origins`, whose statement selects the origin batch's `intent`
and `assessment` on every row. The page uses the assessment's `effects` (batch id,
policy digest, `as_of`), and `read_origins` hashes the request against the batch's
`request_hash`. On `company-on` the 77 saved
batch requests total 2,553 MB, the largest 141 MB, so one page of masters from
one large batch returns that request once per master: `read_origins` reads 200
masters a statement, about 28 GB for the largest batch, and macOS killed the process (signal 9) before the first page
arrived, twice. Any consumer reading masters of a store loaded in large batches
meets the same limit; the hosted store too.

Not on the merge path (2026-10-28, ticket 146): the merge's record reads select no batch
request; `read_origins` is also called for relationships (none in `company-on`)
and, in `reconcile`, for reviews a run's own batches touched, whose latest batch
is that run's.

## Parts

- [x] GoF consult (2026-10-29 07:10 ET): leave the adapter's shape; the change stays inside `read_origins` and its
  statement (one more bounded statement, `origin_requests_statement`, by primary key); the `Store.adapter()` note
  stays its own change
- [x] Read a batch's request once per call (the distinct batch keys), not once per row, keeping its hash check
  (2026-10-29 07:10 ET): `origin_statement` no longer selects the request or the assessment;
  `origin_requests_statement` reads each distinct batch's request, request hash and assessment once, by primary
  key, and checks the request against its hash once; every record of the batch shares those bytes. Found: on
  PostgreSQL the statement's `LATERAL ... OFFSET 0` subqueries selected every column of the batch, proposal and
  run tables, so the batch's request and the proposal's own copy of it were still in the plan; each now names
  only the columns it uses
- [x] A test: a page of masters from one batch reads that batch's request once (2026-10-29 07:15 ET):
  `master_read_scenarios.py` case `one_request`: three masters saved in one batch, a `snapshot_page` of every
  master runs one statement that reads the request, the per-record statement never names it, the masters' requests
  are equal, and the per-batch read is a primary-key seek on both engines; seen to fail on the old code; the
  origin-reading adapter tests 48 passed on PostgreSQL (5 min 5 s) and 48 on MySQL (4 min 14 s)
- [ ] ~~GoF note~~ noted (ticket 146's review): eight call sites in six files build the storage adapter by hand (`storage_adapter().Adapter(...)`); #1171 changed four at once. A `Store.adapter()` would make the next change one edit; its own small change
- [x] Learning → skill (2026-10-29 07:43 ET): `skills/mdm-engineering/SKILL.md`: a read of records reads each
  batch's request once; a read selects only the columns it uses (a `LATERAL ... OFFSET 0` subquery keeps every
  column of its table). Published with Codex's pending skill draft, which the overlap guard had stopped
- [x] Three-axis review (2026-10-29 07:15 ET). GoF: leave it. Standards: every check kept (batch and run hashes,
  the request against its hash, the origin event, the generation; a batch missing from the second read raises);
  the per-batch read is now one primary-key probe a batch (a plain `IN` gave PostgreSQL a bitmap scan) and the
  test proves the seek on both engines; the test matches the qualified column and states equal requests, not
  object identity. Spec: accepted; the test now pages masters through `ContractReader.snapshot_page` (one
  statement reads the request for the whole page). Noted: a page's memory is now bounded by its distinct
  batches, not its masters; a page spanning many large batches still holds each of their requests once;
  `snapshot_page` calls `read_origins` again only when it skips future objects, and then reads a batch once a call
- [x] PR, CI, merge (2026-10-29 07:33 ET): #1217 merged, 20 of 20 checks
