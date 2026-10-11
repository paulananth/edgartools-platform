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
- [x] GoF consult: one owner already exists (`batch`, every table carries `batch_id`); the root is copying at each handoff; the same problem was fixed piecemeal three times (#751, #772, #906). Order: outbox by batch, Company fields once, the write once. Leave: the Stage's reading (five tuned lookup indexes read it; joining every past reading risks matching speed for 2.75 MB), per-field constants (a shape change gives every Company one extra version; about 5%), the proposal's `command` (needed: the readings are not saved yet), the publication key (small). 2026-10-11 12:13 ET
- [x] Outbox rows name their batch (014): a new row keeps only the hash; what it sends is the view `mdm.outbox_delivery`, built from the batch row (a view, because `migrate` revokes every function from PUBLIC and a verifier login holds SELECT only); a row stored before keeps and sends its own payload. The built payload and hash equal what the 001 write stored, for journal, export and graph (`test_clean_outbox_names_batch.py`). `4e82b555` 2026-10-11 12:13 ET
- [ ] ~~`batch.effects` keeps what only it holds; readings and decisions it names by id~~ deferred to its own ticket: `effects` is the Change Journal's payload (014 builds the journal row from it) and the history `consumer.py`, `run.py` and `010` read; its shape is a consumer contract. 1.4 MB of the 16.5 MB left after one batch
- [ ] ~~`stage_record` names its winning reading by `assertion_id`; readers join `source_reading`~~ not recommended by the GoF consult: five tuned lookup indexes read `stage_record.reading` (`001:1472-1480`, `005:15`, `007:75`; #774, #894); a join to every past reading risks matching speed for 2.75 MB. Revisit with a measured matching benchmark
- [x] `company.fields` dropped (015): it was `body->'fields'` again; `company_master_field` reads `body`; versions stored before read the same after (`test_clean_company_fields_once.py`). 2026-10-11 12:13 ET
- [ ] ~~A golden record's field keeps its winner once; the policy digest and kind version once per record~~ deferred (GoF): changing the record's shape trips the no-change check (`001:998-999`), so every Company gets one extra version on its next touch, and the views need a fallback for old rows; about 5% of time measured
- [x] The write runs once: `apply` with identity work assesses once (no `preview_batch`, no second computation), commits the proposal before any master write (Q13 kept; `save_batch` refuses a proposal from its own transaction), then saves the computed batch after re-checking its snapshot and each rule proposal under the lock (`_save_assessed`). A refused batch keeps a rejected proposal; a stale one is superseded and re-proposed (the concurrent-correction test injects its race at the save). `assess`/`apply_assessment` keep the preview for a proposal made on its own (`test_clean_assess_and_apply.py`). 2026-10-11 12:13 ET
- [ ] ~~The publication key once per batch, not per reading~~ not recommended (GoF): 0.45 MB; it is part of each reading's identity
- [x] Each change tested on a populated store: old outbox rows (014) and old Company versions (015) installed by the 001 functions, then read after the migration. 239 MDM Postgres tests pass (1 xfail), with the views and schema-comment tests. 2026-10-11 12:13 ET
- [x] Measured after, chunk 1 (919 Companies), fresh PG16: mastering 11.3–11.4 s to 6.6 s (−42%; one `save_batch` 4.5–4.7 s, no preview); the store after one batch 36.2 MB to 16.5 MB (−54%): outbox 5.4 to under 0.2, `company` 5.1 to 1.9, `batch` 2.7 to 1.4, `stage_record` 11.7 to 6.1 and `source_reading` 7.4 to 4.3 (those two carried dead rows from the rolled-back preview). 2026-10-11 12:13 ET
- [x] Mastering equal before and after: the full installed proof on this branch, on the 7 raw-capture cm27 bundles, passed 12:47–13:14 ET: 6,414 Companies; GLEIF 3,716 records, 3,052 bound (2,861 by name and jurisdiction, 191 by name and postal code); bindings `9216cc18…`, equal to the checkout replay and to #905's proof on the same bundles; recovery on attempt 2; the second pass changed nothing. Faster than #905's proof on the same inputs: SEC merge 4.0 to 2.8 min, GLEIF merge 1.9 to 1.3 min, whole proof 26.5 to 24.3 min. Report `evidence/installed-company-proof-20261011.json` sha256 `95b763b0…`. 2026-10-11 13:14 ET
- [x] Three-axis review of #907. GoF: leave `_execute`'s structure for this PR (split it into a shared prepare and one ending per mode when the next mode comes). Standards: no hard violation; every copied function differs from 001 only where intended. Spec: two faults fixed in `3024c745`: an unrelated batch saved between assessment and save failed the save on its fixed generation (the spec says it must not), so the save takes the current generation under the lock after its checks; a batch refused at save left no rejected record, so it now keeps one. The save had skipped the missing-policy check; the policy and rule-proposal re-check are one method. `candidate-assessments.md` describes the new apply path. Tests for both faults. 2026-10-11 12:18 ET
- [ ] CI green, merge on the operator's word

## Earlier (superseded by the root cause above)

- [x] First measurement (06:54 ET): removing only the per-field repeats cut the save request 14% and mastering about 5%; parked on that, then un-parked by the operator.
