# 06 — Fix the publish/merge-side non-streaming buffer this map deferred

## Question

Ticket 04's streaming hydrate fix (PR #392) only fixed the *download* side
of `_publish_silver_database_if_remote`. Ticket 02's own text named three
remaining full-buffer points as deferred, not fixed:

1. `canonical_local.write_bytes(read_bytes(context.storage_root.join(relative_path)))`
   — full canonical re-download inside the publish/merge step itself.
2. `payload = merged_local.read_bytes()` — full merged-file read before
   upload.
3. Inside `object_storage.py`'s `promote_staged`:
   `staged_bytes = read_bytes(...)` — re-downloads the object step 2 just
   uploaded, fully buffered again, before the conditional `put_object`.

The map's own close-out (Decisions so far, task-profile-revert entry) flagged
this explicitly as unresolved risk: *"checked live 2026-08-20 at 1.5GiB
canonical, comfortably inside medium's 4096MB, with real but shrinking
headroom as canonical grows."*

That headroom ran out. Live in this session (2026-08-22): a real
`merge_candidate_into_canonical` table-scoping fix (separate work, not part
of this map) was deployed and verified working — only the single
genuinely-changed table (`sec_company_ticker`) was merged. `seed-universe`
still OOM'd (exit 137, medium/4096MB) immediately after that merge
completed, with zero further log events — isolating the death to exactly
this deferred file-transfer boundary, not the merge logic.

What is the fix, and is it a new parallel code path or a change to the
existing shared functions?

## Answer

**Widen the existing bytes-based functions to also accept a `Path`, via
`isinstance` dispatch — do not add parallel file-based sibling functions.**

A `/gof-refactor-reviewer` pass (this session) was run specifically to
adjudicate this before writing code, because the user flagged "it cannot
OOM, there is a design flaw" and asked for a pattern review first. Its
finding: this exact boundary has already regressed once. `37c3171f` (May)
fixed `_publish_silver_database_if_remote` to stream via
`context.storage_root.upload_file(...)`. `dc9e6925` (~10 days before this
ticket, the commit that introduced the whole merge/`PromotionConflictError`
concurrency-safety system) silently reintroduced bytes-based
`read_bytes()`/`write_bytes()` for the new upload step, without anyone
noticing the earlier fix had been lost — because nothing tied the two
together. A second, parallel set of file-based functions would leave that
same trap in place: whichever form a future change touches, the other one
silently drifts again.

The chosen design instead unifies the two representations at the one place
that actually cares — `write_staged_bytes`, `promote_staged`, and
`stage_and_promote` each take `payload: bytes | Path`, normalize once
internally (`io.BytesIO(payload)` / `payload.open("rb")`, size from
`len(payload)` / `payload.stat().st_size`), and every existing bytes caller
(including the shard-publish sibling path, `_publish_shard_if_remote`, and
`tests/unit/test_object_storage_conditional_promotion.py`'s exact
`put_object` call-shape assertions) is untouched — `isinstance` dispatch is
backward compatible by construction. `boto3`'s `put_object` `Body` parameter
already accepts any file-like object, so this isn't adding a capability S3
doesn't have; it's removing an artificial bytes-only constraint the
function never needed.

This also eliminates redundant work, not just streams it: once
`stage_and_promote` is passed a `Path`, `promote_staged` can reuse that same
local file instead of re-downloading the object it (or its caller) just
uploaded — closing point 3 above by removal, not by streaming a
still-redundant round trip.

**Rejected alternative:** parallel `write_staged_file()`/
`promote_staged_file()` functions alongside the existing bytes-based ones.
Rejected specifically because it repeats the structural shape that caused
this exact regression once already — a fix landing in one form with no
mechanism forcing the other form to stay in sync.

**Steps (not yet executed as of this ticket's resolution):**
1. Small internal helper, `_as_readable_stream(payload: bytes | Path) ->
   tuple[IO[bytes], int]`, tested in isolation.
2. Widen `write_staged_bytes`'s payload type using the helper.
3. Widen `promote_staged`'s `payload` parameter the same way; re-run
   `test_object_storage_conditional_promotion.py` unchanged — must pass
   with zero edits, proving bytes callers are unaffected.
4. New tests: a `Path`-based call into `promote_staged`/`stage_and_promote`
   produces identical `IfMatch`/`IfNoneMatch`/conflict behavior to the bytes
   path, against a fake S3 client.
5. Only then touch `_publish_silver_database_if_remote`: swap
   `read_bytes`+`write_bytes` for `context.storage_root.download_file(...)`
   (already exists, zero new code) for the canonical re-download, and pass
   `merged_local` (a `Path`) directly into `stage_and_promote` instead of
   `merged_local.read_bytes()`.
6. Empirically re-verify: rebuild/push the warehouse image, redeploy,
   re-run `seed-universe` a third time, confirm no OOM.

**Status:** resolved and verified live, 2026-08-22. Committed as `5c7409a8`.
Built and pushed as `warehouse-sha-5c7409a85457`/`warehouse-prod`
(digest `sha256:5cec2c7b...`), deployed to prod via `deploy-aws-application.sh
--env prod --enable-mdm` (task def `edgartools-prod-medium` → revision 221).

Step 6 (empirical re-verification) confirmed clean:
execution `seed-universe-verify-streaming-fix-1787441504` — `SUCCEEDED`,
`ExitCode: 0`, still on `medium` (1024 CPU / 4096MB, no profile bump
needed), ~5m8s wall time. CloudWatch logs confirm both fixes working
together end to end against the real 1.59GB canonical (`size_bytes:
1590702080`): `silver_table_merge_started`/`merged` fired for exactly
`sec_company_ticker` (the table-scoping fix from the prior commit), and
`silver_publish_started` → `silver_publish_completed` completed cleanly
around it (this ticket's streaming fix) with no OOM.

Bonus, not part of this ticket's original scope but closed as a side
effect: this run also populated `sec_company_ticker` (20,806 rows) for the
first time since the silver-landing-zone migration, closing the
`TICKER_REFERENCE` empty-gold-table gap flagged in CLAUDE.md's
"SNOWFLAKE_RUN_MANIFEST_TASK / silver-loader OPERATE+SELECT gap" entry —
`snowflake_export_row_counts` shows `ticker_reference: 10403` written to
the export manifest for `LOAD_SILVER_LANDING_TASK`'s next cycle to pick up.
