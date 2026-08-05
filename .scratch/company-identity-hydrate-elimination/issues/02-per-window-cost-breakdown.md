# What is Stage0CompanyIdentity's actual per-window cost breakdown (hydrate vs. merge-publish), and would a minimal/selective hydrate be enough on its own?

Type: research
Status: resolved

## Question

We know two things cost something on every Stage0CompanyIdentity window
today: (1) `_hydrate_silver_database_from_storage` (full canonical
download+open) and (2) `_publish_silver_database_if_remote` →
`merge_candidate_into_canonical` (shutil.copy2 of canonical + ATTACH +
per-protected-table walk + per-changed-row Python loop, ~21 tables). We
don't yet know their relative weight, or whether fixing only #1 would
leave #2 as a comparable bottleneck across load_history's 53 windows.

Investigate, using real evidence (code + CloudWatch/logs from the live
runs already in this repo's history — the failed execution `load-history-
1785942443` and its retries against window offset=0/limit=500 are a real
data point, plus the earlier `ReduceIdentityRefresh` measurement of ~188s
for 4 candidates against a ~1021.8MB canonical referenced in this map's
Notes):

1. Read `_publish_silver_database_if_remote`'s skip-if-unchanged fingerprint
   check (`compute_silver_fingerprint`, release-readiness ticket 79). For
   a company-identity window that only touches a handful of small tables
   (`sec_company`, `sec_company_filing`, `sec_company_address`, `sec_
   company_former_name`), would most windows actually hit this no-op skip
   in practice, or does something about company-identity's write pattern
   (e.g. touching `sec_company_filing` on every window) defeat it?
2. Characterize what `merge_candidate_into_canonical`
   (`edgar_warehouse/silver_protection.py`) actually costs as a function of
   canonical DB size vs. candidate/delta size — is the ~21-table
   `information_schema` walk + per-table comparison cost dominated by
   canonical's total size (in which case a smaller candidate doesn't help
   much) or by how much actually changed (in which case avoiding needless
   touches to unrelated tables matters)?
3. Would restricting the *hydrate* step to only the tables company-identity
   mode actually reads/writes (skip `sec_thirteenf_holding`, `sec_
   financial_fact`, etc. via selective DuckDB ATTACH + targeted table copy
   instead of a full file download) meaningfully reduce peak memory on its
   own, holding the current per-window publish step constant? Would it
   also reduce publish cost (a smaller local candidate DB), or is publish
   cost driven by canonical's side of the merge regardless of candidate
   size?
4. Given ticket 01's findings on the delta-then-reduce alternative, produce
   a rough order-of-magnitude comparison: selective-hydrate-keep-per-
   window-publish vs. delta-then-reduce, for a 53-window load_history run
   against current canonical size. Doesn't need to be precise — needs to
   be enough to tell which family of fix is worth pursuing first.

Report findings with a clear recommendation on whether minimal-hydrate
alone is sufficient, or whether the per-window publish cost also needs to
change.

## Answer (2026-08-05)

**Verdict: selective hydrate alone is not sufficient. It fixes the OOM
(peak memory), but leaves a per-window full-canonical merge-publish cost
in place that is structurally decoupled from hydrate and scales with
canonical's total size × 53 windows regardless of candidate size —
plausibly the larger of the two costs at scale, not a minor residual.**

### Q1 — Does the fingerprint skip (ticket 79) let most windows no-op?

No, not for the workload this ticket is about. The mechanism is real and
wired correctly (`_hydrate_silver_database_from_storage` snapshots
`compute_silver_fingerprint` into a sidecar right after hydration —
`edgar_warehouse/application/warehouse_orchestrator.py:912-917`;
`_publish_silver_database_if_remote` recomputes the candidate's current
fingerprint and skips the whole merge/upload/promote cycle on an exact
match — `warehouse_orchestrator.py:960-985`), and it fires unconditionally
for windowed company-identity calls, since the windowed branch always
hydrates (`edgar_warehouse/application/commands/bootstrap_fundamentals.py:133-134`).

But company-identity mode's entire purpose is to land brand-new
`sec_company`/`sec_company_filing`/`sec_company_address`/
`sec_company_former_name` rows for CIKs not yet captured
(`bootstrap_fundamentals.py:246-278`, `_run_submissions_bronze_then_silver`
with `load_mode="company_identity"`), plus `sec_company_ticker` via
`_sync_reference_data` (`warehouse_orchestrator.py:4736-4752`) when no
`identity_refresh_run_id` is set — 5 protected tables touched per window,
not 1. On a genuine bootstrap (the exact scenario that OOM'd:
`load_history`, window offset=0/limit=500, first pass over a new company
universe), essentially every window inserts real new rows into at least
`sec_company_filing`, so `compute_silver_fingerprint`'s per-table
`(row_count, BIT_XOR(HASH(...)))` pair (`silver_protection.py:517-563`)
changes and the skip never fires. The skip *would* fire reliably on a
**re-run over an already-loaded universe** (true no-op re-processing,
where SEC data idempotency means nothing new is written) — but that is a
different call pattern from the one that produced the 2026-08-05 OOM.
Conclusion: don't rely on ticket 79's skip to save Stage0CompanyIdentity's
first-load cost; it's a real optimization for a different case.

### Q2 — Is `merge_candidate_into_canonical`'s cost driven by canonical's size or by what changed?

Both, but the **canonical-size-driven part is unconditional and dominates**.
Two independent cost centers inside `merge_candidate_into_canonical`
(`edgar_warehouse/silver_protection.py:566-775`):

1. **`shutil.copy2(canonical_path, output_path)`** (`silver_protection.py:595`)
   — one full local copy of the *entire* canonical file, unconditional,
   run once per call, before any table is inspected. Cost is purely a
   function of canonical's total on-disk size (order 1GB+ and growing);
   completely independent of candidate size, delta size, or how many rows
   actually changed.
2. **Per-table delta computation** — genuinely bounded by what changed:
   `_delta_rows_as_dicts` (`silver_protection.py:416-462`) materializes
   only the anti-join delta into Python (not the full candidate table),
   and `_matching_canonical_rows_as_dicts` (`silver_protection.py:469-514`)
   is a targeted `WHERE (keys) IN (VALUES ...)` lookup keyed to the
   candidate's own business keys — confirmed by its own docstring and by
   [pipeline-throughput-architecture ticket 05](../../pipeline-throughput-architecture/issues/05-decide-silver-merge-storage-path.md)'s
   fresh `/gof-refactor-reviewer` pass that this was already fixed (commits
   `#211`/`#215`) specifically to avoid a full-table scan/OOM. This part
   scales with candidate/delta size, not canonical's total row count. The
   `PROTECTED_TABLE_REGISTRY` walk itself (~21 entries,
   `silver_protection.py:635-762`) is O(21) dict-membership checks for
   tables the candidate has no data for — negligible regardless of scale.

So a smaller candidate shrinks cost center #2 but has **zero effect** on
#1, and #1 is not a small fraction: it's a full-file local I/O copy of
canonical's entire content, paid every single merge call.

### Q3 — Would selective hydrate reduce publish cost too?

**No.** This is the central finding. `_publish_silver_database_if_remote`
does **not** reuse whatever `_hydrate_silver_database_from_storage`
downloaded — it independently re-downloads canonical fresh from S3 at
publish time (`baseline = context.storage_root.read_object_version(...)`;
`canonical_local.write_bytes(read_bytes(context.storage_root.join(relative_path)))`,
`warehouse_orchestrator.py:987-993`), then calls
`merge_candidate_into_canonical(source_path, canonical_local, merged_local)`
(`warehouse_orchestrator.py:995`), whose `shutil.copy2` target is
`canonical_local` — that fresh download — never the locally-hydrated
candidate file. `read_bytes` itself is a whole-object GET with no
range/partial read (`edgar_warehouse/infrastructure/object_storage.py:449-458`).
Then the merged result is fully re-read (`payload = merged_local.read_bytes()`,
`warehouse_orchestrator.py:997`) and fully re-uploaded
(`write_staged_bytes`, `warehouse_orchestrator.py:1002`). Every one of
these four operations (S3 GET, local copy2, local read, S3 PUT) is sized
to canonical's *current total size on the remote/canonical side*,
regardless of what hydrate loaded in or how small the candidate is.
Restricting hydrate to `sec_company`/`sec_company_filing`/
`sec_company_address`/`sec_company_former_name`/`sec_raw_object` would fix
peak memory during hydration and during `open_silver_database` (the OOM's
actual root cause) — but publish's cost is architecturally decoupled from
hydrate and would be completely unchanged by that fix.

(Secondary observation, not scored as part of this ticket's core
question: hydrate and publish each independently pull canonical's full
bytes from S3 within the same window — two full-object GETs of
essentially the same object back to back. Unlike
[release-readiness ticket 76](../../release-readiness/issues/76-fix-reduce-identity-refresh-double-fetch.md)'s
true same-call redundant fetch, this one may be load-bearing for
concurrency correctness — publish's fresh read is what lets
`promote_staged`'s ETag check detect a canonical change that happened
*after* hydration — so collapsing it isn't obviously free; flagging for
ticket 03/01 to weigh, not resolving here.)

### Q4 — Order-of-magnitude: today's per-window shape vs. delta-then-reduce, 53 windows

No direct CloudWatch timing exists for Stage0CompanyIdentity's own
hydrate/publish calls (the OOM killed the task before completing a
window, and no live measurement of a successful window has been captured
in this repo yet) — this is a back-of-envelope estimate anchored to the
one real measurement available for this exact merge machinery: [ticket
05](../../pipeline-throughput-architecture/issues/05-decide-silver-merge-storage-path.md)'s
**187.9s wall-clock for `ReduceIdentityRefresh`** (1 canonical S3 GET + 4
sequential `merge_candidate_into_canonical` calls, each with its own local
`shutil.copy2`, + 1 final local read + 1 S3 PUT — call it ~7
canonical-sized I/O legs) against a **1021.8MB** canonical, i.e. roughly
~27s per canonical-sized I/O leg. (Canonical is very likely larger than
1021.8MB by the time of this ticket's 2026-08-05 OOM — that measurement is
from an earlier session — so if anything this underestimates today's real
cost.)

Reading `reduce_identity_refresh` end to end
(`edgar_warehouse/application/identity_refresh_publication.py:186-346`)
confirms its structural advantage directly: the canonical S3 GET
(`baseline_payload = read_bytes(...)`, line 243) and the final S3 PUT
(`write_staged_bytes`, line 299) each happen **exactly once per reduce
attempt**, regardless of how many candidates (N) are folded in — only the
local `shutil.copy2` (cheap, local-disk) and the small per-table delta
computation repeat per candidate (`current = merged` chaining, lines
264-289). This is the opposite shape from Stage0CompanyIdentity's current
per-window path, where the two expensive *network* legs (S3 GET + S3 PUT)
repeat on **every window**.

Today's shape, per window: hydrate = 1 S3 GET + 1 local write
(`warehouse_orchestrator.py:899-903`); publish = 1 S3 GET + 1 local
copy2 + 1 local read + 1 S3 PUT (`silver_protection.py:595`,
`warehouse_orchestrator.py:987-1002`). ≈5-6 canonical-sized I/O legs per
window × ~27s/leg ≈ **~135-160s/window** for hydrate+publish I/O alone,
on top of the window's legitimate SEC-fetch work. Across 53 windows:
**53 × ~145s ≈ 128 minutes (~2.1 hours)** of repeated full-canonical I/O
— and this *grows* across the run, since canonical itself grows with
every window's successful publish, so window 53 moves more bytes than
window 1.

Delta-then-reduce shape, same 53-window batch: 1 S3 GET + 1 S3 PUT total
(paid once, not 53×) + 53 cheap local `shutil.copy2`s + 53 small delta
computations, i.e. roughly the same order of magnitude as ticket 05's
measured 187.9s-for-4-candidates case scaled to 53 candidates — call it
**on the order of 5-10 minutes total** (local disk copies are far cheaper
per byte than S3 network round trips, and there are only 2 network legs
total instead of 106).

**Rough magnitude: today's per-window publish shape costs on the order of
15-25x more wall-clock than a delta-then-reduce restructuring, for this
I/O class alone, at current canonical size — and that gap widens as
canonical keeps growing.** This is the same direction ticket 01 is
independently evaluating from the generalization-fit angle; this ticket's
finding is that the magnitude is large enough to be worth doing regardless
of how ticket 01's other constraints (barrier semantics, strictness) come
out, not a marginal win.

### Recommendation for ticket 03

Treat this as two separable, both-necessary fixes, not a choice:

1. **Selective/minimal-table hydrate** — fixes the OOM (root cause: peak
   memory during hydration + `open_silver_database`, per the map's
   framing). Necessary, not optional — the task crashes today before
   publish is ever reached.
2. **Restructure the per-window publish** (most likely: adopt
   delta-then-reduce, pending ticket 01's verdict on whether it
   generalizes safely to Stage0's strict sequencing invariant) — fixes a
   separate, comparably large or larger cost (~2 hours of avoidable
   full-canonical S3 I/O across 53 windows, order-of-magnitude estimate
   above) that selective hydrate does not touch at all, because
   `_publish_silver_database_if_remote` re-downloads canonical
   independently of whatever hydrate loaded (Q3).

Doing only #1 unblocks the crash but leaves `load_history`'s
Stage0CompanyIdentity paying roughly an hour-plus of pure repeated-I/O
overhead that a delta-then-reduce restructuring would cut to single-digit
minutes.
