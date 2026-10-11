# Mastering writes each fact once

Operator, 2026-10-11: "why it is growing find root cause"; "fix duplication first"; parked ("Yes") on the
first measurement; then "we must fix duplication in mastering must understand the root cause" (11:4x ET).
Branch `claude/mdm-request-dedup`, worktree `../edgartools-platform-claude-request-dedup`.

## Root cause (measured 2026-10-11 11:45 ET, cm27 chunk 1, 919 Companies, one batch, fresh PG16)

A 1.4 MB records file writes about 35 MB into the store, 25 times its size
(`.scratch/request-dedup/test_where_bytes_go.py`). Each step that touches a
batch keeps its own whole copy of it, instead of naming rows another step
already stored. Nobody measured the bytes until the 16 MB bound failed
(#906).

Copies of one batch (text MB as written; table sizes on disk after one batch:
`stage_record` 11.7, `source_reading` 7.4, `outbox` 5.4, `company` 5.1,
`batch` 2.7, `decision` 1.7, `match_proposal` 1.2):

| Fact | Copies | Where |
|---|---|---|
| Each reading (assertion, 2.75 MB) | 5 | `source_reading.body`; `stage_record.reading` (the same reading, whole); `batch.effects.assertions`; the `journal` outbox row's `effects`; the match proposal's `command` |
| Each golden record (2.8 MB) | 7 | `company.body`; `company.fields` (a part of `body` again); `batch.effects.projections`; the `journal` outbox row twice (`objects` and `effects.projections`); the `graph` and `export` outbox rows |
| Each decision (0.44 MB) | 4 | `decision.body`; `batch.effects`; the `journal` outbox row; the proposal's `automatic` |
| Inside each golden record | per field | the same policy digest and kind version on every field; each winning value twice (`value`, `winner.value`) |
| Inside each reading | per row | one 490-byte publication key on every reading of the batch |

The write itself also runs twice: a batch with a join or merge is first run
through `preview_batch` (all of `write_batch`, then rolled back), proposed,
then run again by `save_batch`. On chunk 1 that is 4.3–4.6 s of preview and
4.4–4.8 s of save: half of mastering's database time repeats the write.

Readers that the fix must keep working:
- `batch.effects->'projections'`: `consumer.py` (history), `run.py`, `010_relationship_version.sql`; `effects->>'as_of'`: `context.py`, `consumer.py`
- `stage_record.reading`: the matching SQL (`matching.py:241-286`), cross references (`005`, `007`)
- the outbox payloads: `journal_delivery.py`, the export and graph publishers (`payload_hash` checked on delivery)

## Parts

- [x] Root cause measured and written above. 2026-10-11 11:50 ET
- [ ] GoF consult on the plan (`write_batch`, `merge.py` `_execute`/`assess`, `consumer.py`, `journal_delivery.py`)
- [ ] Outbox rows name their batch, not a copy: a consumer's payload is built from the stored batch at delivery, its hash kept (`journal`, `graph`, `export`)
- [ ] `batch.effects` keeps what only it holds; readings and decisions it names by id (their own tables hold them)
- [ ] `stage_record` names its winning reading by `assertion_id`; readers join `source_reading`
- [ ] `company.fields` is not stored beside `company.body` (or the reverse), one owner
- [ ] A golden record's field keeps its winner once; the policy digest and kind version once per record, not per field
- [ ] The write runs once: no `preview_batch` re-run of the whole write before a proposal, if the proposal can be checked without it
- [ ] The publication key once per batch, not per reading
- [ ] Each change tested on a populated store (stored rows of the old form still read); migration per change
- [ ] Measured after: bytes per table and mastering time on chunk 1, against the numbers above
- [ ] Mastering equal before and after: chunk 1 golden records, bindings and reviews; the full installed proof (6,414 Companies, 3,052 GLEIF bindings, `9216cc18…`, unchanged second pass)
- [ ] Three-axis review, CI green, merge on the operator's word

## Earlier (superseded by the root cause above)

- [x] First measurement (06:54 ET): removing only the per-field repeats cut the save request 14% and mastering about 5%; parked on that, then un-parked by the operator.
