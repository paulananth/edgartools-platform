# The Merge Stage writes each fact once

Operator, 2026-10-11 ("why it is growing find root cause"; "approved, yes" to opening this ticket).
Branch `claude/mdm-request-dedup`, worktree `../edgartools-platform-claude-request-dedup`. Operator, 2026-10-11 06:50 ET: "fix duplication first", before L4's remaining parts (#905).

## Finding (SEC cm27 chunk 1, 919 Companies, saved save request and match proposal of 2026-10-10)

- Records file 1.4 MB; save request 6.1 MB (x4.4); match proposal before #906 9.6 MB (x7). #906 removed the save request from the proposal; this ticket is the growth inside the save request
- Assertions 2.6 MB: the record's fields 0.4 MB, provenance 1.4 MB; one publication key (490 bytes, 1 distinct) on all 919 assertions, 0.45 MB
- Golden record projections 2.8 MB (919 entities, 47 reviews): about 6 fields each (5,393). Constant on every field: the policy digest and kind version, about 0.65 MB; each value stored twice (`value` and `winner.value`), 0.17 MB. The winner's source, assertion id and record key vary by field and stay
- The constant duplication is about 1.3 MB of 6.1 MB (21%): projections 0.8 MB, publication key 0.45 MB. Provenance constants (about 0.5 MB on the raw path) stay: the assertion id hashes the delivered record
- Decisions, identities, deferred records 0.7 MB
- Mastering time is 87% database (`save_batch` 6.3 s, `preview_batch` 5.7 s over the 6 MB request): the bytes are also the time

## Parts

- [x] Do the bytes drive the time? Chunk 1 mastered into fresh PG16 stores, twice each, as today and with `winner.value` and the per-field policy digest and kind version removed (`.scratch/request-dedup/test_bytes_time.py`): request 6.09 MB to 5.21 MB (-14%); `save_batch` 4.63/4.75 s to 4.47/4.37 s; `preview_batch` 4.55/4.27 s to 3.98/4.21 s; merge 11.43/11.33 s to 10.64/10.85 s (about -5%). The bytes are not the time: the database's time goes to row work, not to reading the request. The fix buys size headroom (the request about 21% smaller), not speed. 2026-10-11 06:54 ET

- [ ] GoF consult on `merge.py` (request assembly), the projection body and `save_batch`
- [ ] The publication key once per batch, not per assertion (what reads it per assertion, and the stored `mdm.assertion` form)
- [ ] Per-field constants (policy digest, kind version) once per golden record or batch; no second copy of the winning value
- [ ] A migration for the stored forms, tested on a populated store (stored old-form rows still read)
- [ ] Measured on chunk 1: request bytes and `save_batch`/`preview_batch` time, before and after
- [ ] Mastering equal before and after: 6,414 Companies, 3,052 GLEIF bindings, bindings `9216cc18…`, a second pass changes nothing
- [ ] Three-axis review, CI green, merge on the operator's word
