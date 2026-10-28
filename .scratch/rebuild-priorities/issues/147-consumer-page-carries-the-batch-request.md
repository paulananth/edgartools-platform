# 147: A consumer page carries each master's whole saved batch request

Priority: 147. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 14:20 ET.

Type: bug. Status: open. Found by ticket 146.

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

- [ ] Read a batch's request once per page (the distinct batch keys), not once
  per row, keeping its hash check (selecting only the provenance would drop that check)
- [ ] A test: a page of masters from one batch reads that batch's request once
- [ ] ~~GoF note~~ noted (ticket 146's review): eight call sites in six files build the storage adapter by hand (`storage_adapter().Adapter(...)`); #1171 changed four at once. A `Store.adapter()` would make the next change one edit; its own small change
- [ ] Learning → skill
