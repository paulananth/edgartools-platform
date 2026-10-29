# 147: A consumer page carries each master's whole saved batch request

Priority: 147. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 14:20 ET.

Type: bug. Status: in progress (Claude, branch `claude/t147-batch-request-once`). Found by ticket 146.

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
- [x] A test: a page of masters from one batch reads that batch's request once (2026-10-29 07:10 ET):
  `master_read_scenarios.py` case `one_request` (three readings of one batch: one statement reads the request,
  the per-record statement never names it, every record shares the same bytes); seen to fail on the old code;
  the origin-reading adapter tests 48 passed on PostgreSQL (5 min 34 s, sharing cores with ticket 120's load)
  and 48 on MySQL (3 min 28 s)
- [ ] ~~GoF note~~ noted (ticket 146's review): eight call sites in six files build the storage adapter by hand (`storage_adapter().Adapter(...)`); #1171 changed four at once. A `Store.adapter()` would make the next change one edit; its own small change
- [ ] Learning → skill, written, waiting: `skills/mdm-engineering/SKILL.md` gains "a read of records reads each
  batch's request once" (replacing "a consumer page reads each master with its batch's request, once a row") and
  "a read selects only the columns it uses: a `LATERAL ... OFFSET 0` subquery keeps every column of its table".
  Not edited yet: Codex's worktree `codex/test-audit-skill-20261028` holds uncommitted changes to that file (no
  PR; overlap guard, 2026-10-29 07:10 ET); added once that change lands
- [ ] Three-axis review; PR, CI, merge
