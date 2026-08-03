Type: task
Status: open

## Question

`daily-incremental-ticket70-verify-1785720814` (started 2026-08-02T21:33:36-04:00,
stopped 2026-08-03T06:08:19-04:00 after this investigation) never had a chance to
succeed: it retried `RunWarehouseTask` 4 times, each attempt burning ~85 minutes
redoing the full 10,491-CIK submissions/silver pass, then failing identically at
the final artifact-fetch step every time. How should the platform (a) unblock
this specific stuck run and (b) avoid this exact multi-hour blind-retry pattern
recurring the next time a legacy pre-fix object collides with a re-selected
accession?

## Root cause (confirmed live)

Two accessions for CIK `2143673` -- `0000905148-26-003370` and
`0001999371-26-016256`, both Form 3 filings -- were permanently marked
`terminal_repair_required` by `daily_artifact_resume.py`'s immutable-content
guard (`edgar_warehouse/silver_protection.py`-adjacent fail-closed policy, per
[ticket 60](60-decide-durable-daily-artifact-resume-disposition.md)/
[ticket 63](63-implement-durable-daily-artifact-resume-disposition.md)).

Diffed the actual bytes:
- Live SEC content (`curl` against the real archival URL, fetched during this
  investigation): 9971 / 2427 bytes, ends `</ownershipDocument>\n`.
- Bronze-stored content (`aws s3api head-object` + `cp`): 9970 / 2426 bytes,
  ends `</ownershipDocument>` -- **exactly one trailing newline short**, no
  other byte differs.
- Bronze `LastModified`: **2026-07-30T02:11:57Z / 2026-07-30T02:11:58Z**.
- The byte-exact capture fix (`edgar_warehouse/infrastructure/
  filing_content_gateway.py`, "deliberately uses the repository-owned client
  ... so bronze stores the exact archival response, not a library-normalized
  value") landed in commit `5ca30418` at **2026-07-31T16:58:20-04:00** -- over
  a day *after* these two objects were captured.

So this is not a real SEC content change and not a bug in the current fetch/
compare path -- it's these two objects being **pre-fix artifacts**: captured
through the old library-normalized path (which apparently stripped a trailing
newline) before ticket 56 made capture byte-exact. The guard is correctly
refusing to silently overwrite mismatched bytes; it just has no way to
distinguish "genuine SEC content change, do not overwrite" from "known,
one-time capture-format transition, safe to accept the new byte-exact copy."

## What made this expensive, not just blocked

`prepare_resume`'s terminal markers are written once (23:43:59 and 01:27:14
during the *first* attempt) and persist in S3 keyed by `run_id`. Every
subsequent Step Functions retry reused the same `run_id` (`--run-id` is a
fixed CLI arg on the `RunWarehouseTask` ECS override), so every retry saw the
same two markers and failed at the identical final step -- but **only after**
redoing the entire submissions-bronze-capture (~64 min) and silver-apply
(~31 min, confirmed via `silver_apply_completed` `duration_seconds: 1855.7`)
phases from scratch each time, because those phases aren't gated on whether a
prior attempt's terminal-repair block is still unresolved. 4 attempts x ~85
min = ~5.7 hours of compute before this was caught and stopped manually.

Separately: `record_repair_attestation` (`edgar_warehouse/application/
daily_artifact_resume.py`) exists but nothing calls it -- there is currently
no CLI command an operator can run to actually clear a
`terminal_repair_required` marker. It would have to be invoked by hand-writing
Python or the S3 JSON payload directly.

## Not yet specified / needs a scan

Any other bronze primary document captured before 2026-07-31T16:58:20-04:00,
for a form type in `daily-incremental`'s configured set (13F-HR, 3, 3/A, 4,
4/A, 5, 8-K, 8-K/A, DEF 14A, DEFA14A, PRE 14A per the live
`daily_artifact_selection_completed` event), could hit this exact wall the
next time a recurring 7-day window happens to re-select its accession. How
many such objects exist has **not** been measured -- a full bucket scan
(`s3://edgartools-prod-bronze-690839588395/warehouse/bronze/filings/sec/`)
filtered by `LastModified < 2026-07-31T20:58:20Z` was judged too expensive to
run inline during this investigation and needs a bounded approach (S3
Inventory report if one exists, or a scoped scan against only the CIKs/
accessions actually eligible for near-term re-selection) before it's
ticket-able as a fix.

## Immediate unblock (done)

Execution stopped (`stop-execution`, cause recorded), `pipeline_run_lease`
manually released via the same `release-identity-refresh-lease` ECS task
pattern used earlier in this workstream. The two terminal markers were left
in place, not repaired -- repairing them (writing valid
`record_repair_attestation` payloads) is a decision for whoever picks up this
ticket, not something to do silently mid-investigation.

## Repair performed (2026-08-03, explicit user instruction)

Traced why `record_repair_attestation` alone would **not** have been
sufficient: `prepare_resume` moving an attested accession from
`repair_required` back to `pending` only re-admits it into the artifact-fetch
loop -- the loop still calls `fetch_filing_artifacts` -> `_write_raw_artifact`
-> `write_immutable_bytes` unconditionally on the retry, which would hit the
exact same byte mismatch and fail identically again. Confirmed via code
reading (`bronze_filing_artifacts.py:346`, `object_storage.py:265-339`) that
**no code path in this repository can overwrite an existing immutable
object** -- not even the separate `release-mode --force --repair-manifest`
mechanism (`bootstrap-batch`'s CLI-exposed repair path), which also routes
through `write_immutable_bytes` and would hit the identical error. The
attestation mechanism only records operator sign-off that a conflict is
understood; it was never wired to actually change the stored bytes.

Given that, the only correct fix was to correct the stale bytes directly:

1. Re-verified both accessions have exactly one document each (`aws s3 ls
   --recursive` under each accession prefix) -- no other attachments at risk.
2. Confirmed the bronze bucket (`edgartools-prod-bronze-690839588395`) has S3
   versioning **enabled** -- an overwrite is recoverable, not destructive.
   Recorded pre-repair version IDs for both objects before touching them
   (`cKRJt30JV_em3XjdlfFp41IGqaQurpt9`, `kh0Q8Uh.lzNNj6a4V6bwnXdfY1KTUxKE`).
3. Re-fetched live SEC bytes immediately before the repair (fresh `curl`,
   proper `EDGAR_IDENTITY`-equivalent User-Agent) and re-confirmed the diff
   was still exactly the one trailing newline, nothing else.
4. Overwrote both canonical bronze keys directly via `s3api put-object`
   (bypassing `write_immutable_bytes`, which has no override -- this was a
   deliberate, explicit, one-time correction of two specific known-stale
   objects, not a new general capability). New version IDs:
   `ckgRLTHBq5_uAgmYN7ccT4jjcfE9q3Bv`, `LLxEzGcUW_USPAhAK9sOgMdV6B1Y4O.d`.
5. Downloaded both back and byte-diffed against the live SEC fetch --
   confirmed identical.

No `record_repair_attestation` call was needed: the follow-up run uses a
**new** execution/run_id (`daily-incremental-ticket74-repair-verify-1785752569`,
started 2026-08-03T06:22:51-04:00), which has no prior `terminal_repair_required`
marker under its own run-scoped S3 prefix at all. With the bronze bytes now
byte-exact, a fresh fetch for these two accessions will match on the first
attempt and never trip the conflict.

Old `daily-incremental-ticket70-verify-1785720814` execution: stopped, lease
released, **not resumed** -- superseded by the new execution above.

## Done when

A decision exists on: (1) how to repair these 2 known accessions (build the
missing CLI command vs. a one-off manual attestation), (2) whether/how to
scan for and pre-emptively repair other pre-2026-07-31 objects before they
cause the same multi-hour blind-retry pattern again, and (3) whether the
resume/retry loop should gate expensive earlier phases (submissions
bronze/silver) on a cheap up-front check for pre-existing unresolved terminal
markers, instead of redoing ~95 minutes of work before discovering a block
that was already known at the start of the attempt.
