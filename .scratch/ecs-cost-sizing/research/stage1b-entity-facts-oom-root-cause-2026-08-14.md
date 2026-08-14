# Stage1BEntityFacts OOM — root cause (ticket 20's "Not yet answered" section)

Research date: 2026-08-14
Scope: `edgar_warehouse/application/commands/bootstrap_fundamentals.py`,
`edgar_warehouse/application/workflows/fundamentals_ingest.py`,
`edgar_warehouse/silver_store.py`, `edgar_warehouse/silver_protection.py`,
`edgar_warehouse/application/warehouse_orchestrator.py`,
`edgar_warehouse/application/identity_refresh_publication.py`,
`infra/scripts/deploy-aws-application.sh`. Live evidence pulled from
CloudWatch (`/aws/ecs/edgartools-prod-warehouse`) for the three failed task
attempts named in ticket 20, plus one live SEC `companyfacts` fetch used to
ground the memory-expansion estimate in a measured number instead of a guess.

## Headline finding (read this first)

**The `run_bootstrap_entity_facts` per-CIK fetch/parse/merge loop is not the
problem — it is already streaming and completes successfully for the full
500-CIK window in all 3 attempts.** The OOM happens afterward, in the
**one-time silver-publish step** every `bootstrap-fundamentals` mode
(`entity-facts`, `per-filing`, `thirteenf`) shares:
`_publish_silver_database_if_remote` →
`merge_candidate_into_canonical`. That function's delta computation
(`_delta_rows_as_dicts`) does an unchunked `.fetchall()` that, for a
**first-time / cold-start table** (canonical `sec_financial_fact` was
effectively empty before this run — see "Consequence in this run" in the
ticket itself: "zero XBRL entity-facts data ... for the entire CIK universe
from this run"), materializes **the entire candidate table** into a Python
list of dicts, because the anti-join against an empty canonical returns
~100% of candidate rows as "new." All 3 attempts die at the identical
point in the identical table-iteration order: the `silver_table_merge_started`
event for `sec_financial_fact`, with no further log line before the SIGKILL.

This distinction matters for the fix: this is not "the entity-facts fetch
loop needs to stream like `iter_gold_tables()`" (it already does, and always
did) — it is "the publish/merge step, shared by every `bootstrap-fundamentals`
mode, has its own un-streamed accumulate-then-write pattern that a steady-state
incremental resync never exercises at volume, but a cold-start full-universe
backfill does."

---

## Q1 — Does the entity-facts code path stream or accumulate?

### 1a. The fetch → parse → merge loop itself: streams, per-CIK

Entry point: `bootstrap_fundamentals.py:209-230` dispatches `mode ==
"entity-facts"` to `run_bootstrap_entity_facts`
(`edgar_warehouse/application/workflows/fundamentals_ingest.py:360-459`).

That function's `for cik in cik_list:` loop (`fundamentals_ingest.py:395`)
does, per CIK:

1. `fetch_companyfacts_json(int(cik), identity)` (line 409) — one company's
   raw JSON, held only for this iteration.
2. `parse_entity_facts(cik=cik, facts_json=facts_json)` (line 417) — explodes
   that JSON into `sec_financial_fact`/`sec_accounting_flag` row dicts
   (`edgar_warehouse/parsers/financials.py:57-138`).
3. **Immediately merges into the local on-disk DuckDB file** via
   `db.merge_financial_facts(...)` / `db.merge_accounting_flags(...)` /
   `db.merge_financial_derived(...)` (`fundamentals_ingest.py:423-451`), which
   call `SilverDatabase._merge_rows_bulk`
   (`edgar_warehouse/silver_store.py:4298-4356`) — a real `INSERT ... FROM
   _bulk_stage_src` executed against the DuckDB connection immediately, not
   queued. The per-CIK `parsed`/`fact_rows`/`accession_groups` Python objects
   fall out of scope at the next loop iteration.

This is the same shape as `iter_gold_tables()`'s per-item flush, just applied
per-CIK instead of per-table. **Ruled out** as the OOM's cause.

Also checked and ruled out: `LandingExportBuffer`
(`edgar_warehouse/serving/silver_landing_export.py:27-51`), the in-memory
accumulator that *does* hold every row ever merged for a whole command run
(exactly the accumulate-then-flush shape). It is opt-in via
`SilverDatabase(db_path, landing_export=...)`
(`silver_store.py:863-874`), defaulting to `None`
(`edgar_warehouse/silver_support/session.py:13-19`). `bootstrap_fundamentals.py:135`
calls `open_silver_database(context.silver_root)` with **no** `landing_export`
argument, so `db.landing_export is None` for this whole command and every
`@track_landing_rows` decorator on `SilverDatabase` is a no-op
(`silver_landing_export.py:66-75`, checks `if landing_export is not None`).
Confirmed not a contributor to this incident.

### 1b. The publish step: accumulates, once, at the end of the whole window

`bootstrap_fundamentals.py:328-352` calls `_publish_silver_database_if_remote(context)`
**once**, after the entire `cik_list` (500 CIKs) has been processed — this is
unconditional for `entity-facts`/`per-filing`/`thirteenf` (only skipped when
`identity_refresh_run_id` is set, which requires `company-identity` mode with
an explicit `--cik-list`, per the guard at `bootstrap_fundamentals.py:83-85` —
entity-facts can never take that branch).

`_publish_silver_database_if_remote`
(`edgar_warehouse/application/warehouse_orchestrator.py:1045-1133`):

- Downloads canonical's current content fully into memory and writes it to a
  local temp file: `canonical_local.write_bytes(read_bytes(...))`
  (line 1112).
- Calls `merge_candidate_into_canonical(source_path, canonical_local,
  merged_local)` (line 1114).
- **After** the merge returns, reads the entire merged output back into
  memory as one `bytes` object before upload: `payload =
  merged_local.read_bytes()` (line 1116). (Not itself the proximate cause
  here — see the CloudWatch timing in Q2, the task dies *during* the merge
  call, before this line is ever reached — but it is a second, independent
  full-file-in-memory read on the same code path.)

`merge_candidate_into_canonical`
(`edgar_warehouse/silver_protection.py:585-794`) iterates
`PROTECTED_TABLE_REGISTRY` in dict-insertion order
(`silver_protection.py:81` onward: `sec_raw_object` at 138,
`sec_filing_attachment` at 182, `sec_filing_text` at 221,
`sec_financial_fact` at 224 — this exact order is what CloudWatch shows, see
Q2). For each table with candidate data, it calls `_delta_rows_as_dicts`
(`silver_protection.py:435-481`):

```python
result = conn.execute(f"SELECT ... FROM cand.main.{table} c "
                       f"WHERE NOT EXISTS (SELECT 1 FROM out.main.{table} o WHERE {match_sql})")
return [dict(zip(columns, row)) for row in result.fetchall()]   # line 481
```

`.fetchall()` is unconditional and unchunked — no `fetchmany`/batching. Its
own docstring (lines 449-457) explicitly acknowledges the general shape of
this OOM class ("the candidate file can be as large as canonical itself ...
even when a run only touches a few hundred CIKs") and describes the fix that
was already made: computing the delta via a SQL anti-join instead of pulling
every candidate row unconditionally. **That fix assumes the anti-join filters
out most rows** (a steady-state resync where most candidate rows already
match canonical). It provides no bound when the anti-join *doesn't* filter
much — i.e., a **cold-start table**, where canonical has ~nothing to match
against and the "delta" is ~the whole candidate table. That is exactly this
run: ticket 20's own "Consequence" section says this run would have produced
the **first** `sec_financial_fact`/`sec_financial_derived`/`sec_accounting_flag`
data for the CIK universe.

The resulting `candidate_rows` Python list — sized to (effectively) the
window's entire freshly-fetched fact set — is then held for the whole
per-row Python loop at `silver_protection.py:740-773`, which calls
`_insert_row`/`_update_row` (`silver_protection.py:816-827`,
`954-967`) — **one `conn.execute()` per row**, not a bulk statement. This
exact row-by-row shape is already flagged elsewhere in this codebase as a
known anti-pattern: `silver_store.py:4335-4342`'s comment on
`_merge_rows_bulk` documents that `executemany()`-style one-row-at-a-time
inserts measured "~1.5ms/row (measured: 384K rows took 577s here)" and
"pushed a memory-constrained host into swap," which is why `_merge_rows_bulk`
switched to registering an Arrow table and bulk-loading — but that fix was
never applied to `merge_candidate_into_canonical`'s insert/update path.

### 1c. Is Stage0CompanyIdentity's own OOM fix directly reusable?

Yes, in spirit, and it is *already applied to a sibling caller of the same
merge function*, just not this one. `edgar_warehouse/application/identity_refresh_publication.py:reduce_identity_refresh`
(lines 186-355) is the single dedicated reducer for Stage0's Daily Identity
Refresh, and it calls the **same** `merge_candidate_into_canonical`
(imported at `identity_refresh_publication.py:28`). Its docstring
(lines 201-211) records a near-identical incident already fixed once:

> "Regression (2026-08-03, release-readiness ticket 83): an earlier version
> of this fix (ticket 76) held every verified candidate's full bytes in a
> dict for the whole call. ... meant a full canonical-sized reference
> snapshot, every batch delta, *and* the freshly re-read canonical baseline
> all coexisted in process memory at once, stacking with the merge's own
> DuckDB working set — OOM-killed a real prod run (exit 137) mid-merge on the
> largest protected table."

That is the same failure signature as this ticket: OOM (137) mid-merge, on
the largest protected table. The fix that landed there
(`identity_refresh_publication.py:220-306`): write every verified input
straight to local files, never hold full-file bytes across the whole call;
read canonical's bytes once and `del baseline_payload` immediately after
writing to disk (line 246); and merge one candidate at a time in a loop,
deleting each intermediate `merged-{index}.duckdb` as soon as the next one
supersedes it, bounding peak local disk to ~2 canonical-sized files instead
of O(candidate_count).

**Crucially, this precedent fixes the *caller's* byte-holding discipline
(section 1b's first bullet and `payload = ...read_bytes()`), not
`merge_candidate_into_canonical`'s own internal `_delta_rows_as_dicts`
`.fetchall()` / row-by-row insert loop** — that inner pattern is shared,
unfixed code, common to both callers. The identity-refresh reducer's daily
per-batch deltas are small enough in practice that this inner pattern hasn't
(yet) been observed to blow up there; a full-universe entity-facts backfill
is exactly the kind of high-volume, cold-start candidate that exposes it.
So: the *caller-discipline* half of Stage0's fix is directly reusable and not
yet applied to `_publish_silver_database_if_remote`; the *deeper* half (fixing
`_delta_rows_as_dicts`/`_insert_row`/`_update_row` to chunk or bulk-load) has
no working precedent anywhere in this codebase yet — it would be new work,
patterned after `_merge_rows_bulk`'s existing Arrow-based bulk-insert
approach (`silver_store.py:4298-4356`), not a copy of an existing fix.

---

## Q2 — Estimate actual peak memory, don't just guess

### CloudWatch timing: the "consistent ~50 minutes" is fetch-loop network time, not gradual memory growth

Pulled full CloudWatch logs for all 3 task attempts
(`/aws/ecs/edgartools-prod-warehouse`, log group; streams
`warehouse-medium/edgar-warehouse/{7bee7823...,43e9b631...,75fab0bd...}`).
All three streams are **byte-for-byte identical** in event sequence and
counts (488 `sec_call_started`, 330 `sec_call_completed`, 158
`sec_call_failed`/`entity_facts_fetch_error` [SEC 404s for delisted/renamed
CIKs], 12 `entity_facts_silver_skip`; 488 + 12 = 500, matching the window's
full `cik_count`). Computed from attempt 1's timestamps:

| Phase | Duration |
|---|---|
| Total task log span (first to last event) | 3124.4 s (~52.1 min) |
| `run_bootstrap_entity_facts` fetch loop (first `sec_call_started` → last `sec_call_completed`/`failed`) | 3015.6 s (~50.3 min) |
| Gap from last SEC fetch → `silver_table_merge_started` for `sec_financial_fact` | 108.5 s |
| Gap from that event → task death (last log line) | **0.0 s** |

So the fetch loop **completes successfully for all 500 CIKs** and consumes
essentially the entire observed wall-clock duration on its own (real,
rate-limited SEC network I/O — this matches CLAUDE.md's documented per-task
rate-limiting design, not a memory symptom). The publish/merge step then runs
for only ~108 seconds (successfully merging `sec_raw_object`: 352,305 rows
unchanged, and `sec_filing_attachment`: 417,302 rows unchanged — both large
but *unchanged*, i.e., cheap identical-row paths) before the
`sec_financial_fact` merge starts and the container is killed with **no
further log output** — consistent with the OOM happening rapidly (seconds,
not minutes) once that table's `_delta_rows_as_dicts` query and the
downstream Python materialization actually run. The ticket's framing ("a
deterministic memory ceiling being hit at a roughly fixed point in the
window's CIK iteration") is directionally right about determinism, but the
mechanism is not "memory creeps up steadily across 500 CIKs" — it's "500 CIKs
of fetching always takes ~50 minutes and always produces the same-shaped
candidate, so the same single expensive operation (the `sec_financial_fact`
merge) always starts at ~minute 52 and always blows the same budget within
seconds."

### Grounded row-count and memory estimate

Measured directly (not guessed) against one real SEC `companyfacts` payload,
CIK 0000014707 (one of the CIKs in this exact window, 3,532,743 bytes — a
size representative of the ticket's cited 0.5-5.7MB range):

```
$ curl -sS -A "..." https://data.sec.gov/api/xbrl/companyfacts/CIK0000014707.json -o CIK0000014707.json
$ python3 -c "... parse_entity_facts(cik=14707, facts_json=json.load(...)) ..."
rows sec_financial_fact: 23533
```

Measured with `tracemalloc` around the actual `parse_entity_facts` call (real
code, `edgar_warehouse/parsers/financials.py`, not a synthetic estimate):

```
total memory added by parse (tracemalloc): 11,646,696 bytes (11.11 MB)
bytes per fact row: 494.9
```

So: **~495 bytes of Python object overhead per `sec_financial_fact` row
dict**, and **~6,661 rows per raw-JSON MB** (23,533 rows / 3.37 MB) for this
sample.

Extrapolating to the whole window using CloudWatch's own recorded `bytes`
field on every `sec_call_completed` event for attempt 1 (real numbers, not
assumed):

```
successful companyfacts fetches: 330
total raw JSON bytes fetched:     754,634,323  (719.7 MB)
avg bytes/company:                2,286,771
```

Using the measured ratio (0.0066614 rows/byte) from the CIK0000014707 sample:

```
estimated total sec_financial_fact candidate rows this window: ~5,026,918
estimated Python list-of-dicts memory for that many rows:      ~2,373 MB (2.32 GB)
```

That ~2.3 GB is **just** the `candidate_rows` Python list
`_delta_rows_as_dicts` materializes for the single `sec_financial_fact`
table merge (line 481's `.fetchall()`), held for the entire subsequent
per-row insert loop. It stacks with:

- DuckDB's own connection memory, explicitly bounded to **2 GB** by
  `_connect_bounded()` (`silver_protection.py:33-48`,
  `WAREHOUSE_SILVER_MERGE_MEMORY_LIMIT_GB` default `"2"`) — a real, already-
  intentional ceiling (its own docstring: "leaves headroom for the Python
  process's own overhead ... and the container OS" — headroom that this
  candidate-rows list consumes).
- Baseline Python/library process overhead (duckdb, pyarrow, boto3, etc. all
  already imported by this point) — typically several hundred MB for this
  kind of process, not separately measured here.

**~2.3 GB (candidate list) + 2 GB (DuckDB's own explicit bound) = ~4.3 GB**
before counting any process/library baseline — already over a 4096 MB (4 GB)
`medium` task's hard ceiling. This is consistent with, and quantitatively
explains, the exit-137 kill happening within seconds of the
`sec_financial_fact` merge starting, exactly as CloudWatch shows.

**Caveat on the extrapolation:** the per-row expansion ratio was measured
from one company (CIK 14707); real company-to-company variance in fact
density is unlikely to change the order of magnitude (SEC XBRL frame
coverage scales with a company's own filing history breadth, not
idiosyncratically), but the ~5.03M-row estimate should be read as "same order
of magnitude as what actually happened," not an exact reproduction — the
task's own logs don't include a completed `sec_financial_fact` row count
(the process died before `bootstrap_fundamentals_completed` could log
`metrics["rows_financial_fact"]`), so this is the best obtainable estimate
from primary evidence, not a confirmed exact figure.

**CIK-count answer to the ticket's specific ask:** the OOM does *not*
happen at a fixed **CIK count** partway through the window — it happens
after the fetch loop finishes for the **entire 500-CIK window** (488 fetch
attempts + 12 skips = 500/500), during the one-time publish step that runs
once per window regardless of window size. "What fraction of the window was
processed before the kill" is misleading framing for this bug: 100% of the
window's entity-facts fetching succeeded; the failure is downstream of that,
in a step whose cost scales with **how much new data the whole window
produced**, not with "how far into iterating CIKs" the task got.

---

## Q3 — Does the same shape threaten Stage1BPerFiling/Stage1BThirteenF?

**Yes — they share the exact same shared risk surface (the publish step),
confirmed by reading the code, not by inference.** All three
`bootstrap-fundamentals` modes funnel through the identical
`_publish_silver_database_if_remote` → `merge_candidate_into_canonical` call
at the end of their run (`bootstrap_fundamentals.py:328-352`, unconditional
for these three modes). Confirmed in `infra/scripts/deploy-aws-application.sh`:
all three states use the same `wh_medium_arn` task definition
(1024 CPU / 4096 MB, registered at `deploy-aws-application.sh:1176`), the
same `MaxConcurrency: 1`, `ToleratedFailurePercentage: 0`, and the same
windowed-Map/DISTRIBUTED-Map design:

- `Stage1BEntityFacts` / `fundamentals_entity_facts`: `deploy-aws-application.sh:2501-2528`
- `Stage1BPerFiling` / `fundamentals_per_filing`: `deploy-aws-application.sh:2565-2592`
- `Stage1BThirteenF` / `fundamentals_thirteenf`: `deploy-aws-application.sh:2594-2621`

Their own per-item fetch/parse/write loops were also read and are **equally
streaming**, ruling out their own inner loops as an accumulation risk, same
conclusion as Q1a:

- `run_bootstrap_fundamentals_per_filing`
  (`fundamentals_ingest.py:113-357`): `for filing in filings:` loop
  (line 206), merges per-filing immediately via `db.merge_earnings_releases`/
  `merge_executive_records`/`merge_guidance_facts`/`merge_employment_events`
  (lines 275-339) — same per-item-then-write shape.
- `run_bootstrap_thirteenf` (`fundamentals_ingest.py:462-680`+): `for filing
  in filings:` loop (line 521), same per-filing streaming shape (verified
  through line 620; the merge calls for `sec_thirteenf_holding`/
  `sec_thirteenf_filing` follow the identical pattern as the other two
  modes based on the code read so far).

**Whether the shared publish-step risk is actually *realized* for a given
mode/window depends on the per-item fan-out of the table that mode writes,
same mechanism that hit entity-facts:**

- `per-filing` writes `sec_earnings_release`/`sec_executive_record`/
  `sec_guidance_fact`/`sec_employment_event` — fan-out is roughly
  "a handful of rows per 8-K/DEF 14A filing." Materially lower row volume per
  CIK than entity-facts' "every historical XBRL fact for the company in one
  shot." Lower risk, same code path.
- `thirteenf` writes `sec_thirteenf_holding` — fan-out is "N holdings per
  13F-HR filing," and N can be **very large** for big institutional managers
  (thousands of individual positions per single filing is normal for large
  funds). CLAUDE.md's own "INSTITUTIONAL_HOLDS / EMPLOYED_BY" 5-whys entry
  independently confirms this table's scale at full-universe maturity:
  `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING` already has
  **6.8M rows** in prod. A first-time, cold-start `Stage1BThirteenF` window
  that happens to include one or more large 13F filers is structurally just
  as exposed to the same `_delta_rows_as_dicts` unchunked-`.fetchall()` +
  row-by-row-insert pattern as entity-facts was — this has simply not yet
  been *observed* failing (per the ticket), not because the code protects
  against it.

`company-identity` mode is architecturally different and was **not**
re-examined in depth here because it is Stage0's concern, not Stage1B's
(per CLAUDE.md's Phased Pipeline table) — but it's worth noting for
completeness that a windowed (no explicit `--cik-list`) `company-identity`
run also still hydrates the full canonical DB and would go through the same
`_publish_silver_database_if_remote` path (`_resolve_fundamentals_ciks`'s
docstring at `bootstrap_fundamentals.py:126-134` explicitly flags this: "The
windowed case (no `--cik-list`) still hydrates"). Stage0's actual production
usage runs `company-identity` with an explicit `--cik-list` via the
delta-then-reduce `identity_refresh_publication.py` path instead (which
skips hydration entirely per that same docstring), so this exposure is
believed dormant for Stage0's actual call pattern, not exercised — not
independently re-verified against `deploy-aws-application.sh`'s exact
`Stage0CompanyIdentity` invocation as part of this research pass.

---

## Q4 — Recommendation

**Do (d): a combination — an immediate stopgap now, a real structural fix
before the next full-universe attempt at any of these three stages.**

### Stopgap: move all three Stage1B Branch B modes to `large` (2048 CPU / 8192 MB)

The Q2 estimate (~2.3 GB candidate list + 2 GB DuckDB's own explicit bound
≈ ~4.3 GB for *this window's* `sec_financial_fact` merge alone) fits inside
`large`'s 8192 MB with real headroom (~3.9 GB) for process/library baseline
overhead. This should let the current in-flight full-universe backfill
(`ticket42-task35-fulluniverse-retry7` and any retry) get past window 1
immediately. Apply to `Stage1BEntityFacts`, and — given Q3's finding that the
risk is structurally shared, not entity-facts-specific — to
`Stage1BPerFiling` and `Stage1BThirteenF` as well, rather than waiting for
each to independently OOM in a later window with a large 13F filer or a
per-filing-heavy CIK batch.

**This is explicitly a stopgap, not a fix**, for the same reason CLAUDE.md's
own "Gold-build memory / daily_incremental OOM" 5-whys entry already
cautions about pairing a memory bump with an unverified structural claim:
the accumulation is proportional to **how much new data a cold-start window
produces**, not to a fixed per-window constant — a wider window
(`--cik-limit` > 500), a future run over CIKs with denser XBRL history than
this sample, or `Stage1BThirteenF` landing on a window containing several
large 13F filers could reproduce the identical failure at 8192 MB just as
deterministically as it did at 4096 MB. It moves the ceiling; it does not
remove it.

### Structural fix: bound `merge_candidate_into_canonical`'s per-table candidate materialization

Two concrete, code-grounded changes to `edgar_warehouse/silver_protection.py`,
patterned after work this codebase has already done elsewhere for the
identical problem shape:

1. **Chunk `_delta_rows_as_dicts`'s result consumption** (line 481) instead
   of one unconditional `.fetchall()` — e.g. `fetchmany(N)` in a loop, or
   push the insert/update logic into SQL entirely for the common "no
   same-key row exists yet" case (which is exactly what dominates a
   cold-start table) so brand-new rows never need a Python round-trip at
   all, and only genuine same-key conflicts (the case that needs the
   authority-column tiebreak logic in Python) go through the row-by-row
   path.
2. **Replace `_insert_row`'s one-`execute()`-per-row loop with a bulk
   insert**, mirroring `SilverDatabase._merge_rows_bulk`'s already-proven
   Arrow-table-registration approach (`silver_store.py:4298-4356`), which
   this same codebase adopted specifically to fix the "384K rows took 577s ...
   pushed a memory-constrained host into swap" failure mode — the identical
   symptom class, just not yet applied to this call site. Genuinely new
   (as opposed to same-key conflict) rows are exactly the case that can be
   safely bulk-inserted without per-row conflict resolution.

This is the "b" option from the ticket's framing (a genuine streaming/
incremental-flush fix mirroring `iter_gold_tables()`), scoped to where the
evidence actually points — the publish step, not the entity-facts fetch
loop — rather than a guess at what "streaming" would mean for code that
already streams.

### Why not (c) — shrinking `--cik-limit`

Shrinking the per-window `--cik-limit` (e.g. 500 → 100) would reduce a
cold-start window's candidate volume proportionally and could avoid this
specific OOM as a side effect, but it's a weaker, less targeted lever than
either of the above: it doesn't fix the row-by-row insert performance
problem (still ~1.5ms/row per the `_merge_rows_bulk` precedent, just fewer
rows per invocation), it doesn't remove the risk for a future window that
happens to contain a handful of unusually fact-dense companies (variance,
not window size, drives the real risk), and per CLAUDE.md's own "Phased
Pipeline" invariants, Stage 1B's Map already runs at `MaxConcurrency: 1` —
smaller windows only mean *more* sequential windows at the same total cost,
trading a single large risk exposure for many smaller (but not
categorically eliminated) ones. Treat it as a viable **additional** dial to
turn down further if the structural fix above still leaves headroom
concerns for a future denser universe, not as a substitute for fixing
`merge_candidate_into_canonical` itself.
