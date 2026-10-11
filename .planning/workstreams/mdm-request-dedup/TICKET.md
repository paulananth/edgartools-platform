# The Merge Stage writes each fact once

Operator, 2026-10-11 ("why it is growing find root cause"; "approved, yes" to opening this ticket).
Branch `claude/mdm-request-dedup`, worktree `../edgartools-platform-claude-request-dedup`. Starts after Issue 20 L4 (#905).

## Finding (SEC cm27 chunk 1, 919 Companies, saved save request and match proposal of 2026-10-10)

- Records file 1.4 MB; save request 6.1 MB (x4.4); match proposal before #906 9.6 MB (x7). #906 removed the save request from the proposal; this ticket is the growth inside the save request
- Assertions 2.6 MB: the record's fields 0.4 MB, provenance 1.4 MB; one publication key (490 bytes, 1 distinct) on all 919 assertions, 0.45 MB
- Golden record projections 2.8 MB (919 entities, 47 reviews): about 6 fields each; the same policy digest, kind version, source, assertion id and record key on every field, 1.05 MB; each value stored twice (`value` and `winner.value`), 0.17 MB
- Decisions, identities, deferred records 0.7 MB
- Mastering time is 87% database (`save_batch` 6.3 s, `preview_batch` 5.7 s over the 6 MB request): the bytes are also the time

## Parts

- [ ] GoF consult on `merge.py` (request assembly), the projection body and `save_batch`
- [ ] The publication key once per batch, not per assertion (what reads it per assertion, and the stored `mdm.assertion` form)
- [ ] Per-field constants (policy digest, kind version) once per golden record or batch; no second copy of the winning value
- [ ] A migration for the stored forms, tested on a populated store (stored old-form rows still read)
- [ ] Measured on chunk 1: request bytes and `save_batch`/`preview_batch` time, before and after
- [ ] Mastering equal before and after: 6,414 Companies, 3,052 GLEIF bindings, bindings `9216cc18…`, a second pass changes nothing
- [ ] Three-axis review, CI green, merge on the operator's word
