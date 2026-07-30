# 43 — Research findings: SEC daily-index JSON + this repo's daily-form-index pipeline

Feeds ticket 43
(`.scratch/release-readiness/issues/43-investigate-daily-incremental-full-universe-scope.md`).
Written as a durable sibling artifact per this repo's issue-tracker convention, matching the
shape of `.scratch/release-readiness/issues/27-research-findings.md`.

## Method

1. Fetched `https://www.sec.gov/Archives/edgar/daily-index/` and its quarter/day sub-resources
   directly with `curl -A "EdgarTools Platform Research <email>" ...` (SEC blocks generic
   User-Agents with a 403 — the platform's own `EDGAR_IDENTITY` convention, `CLAUDE.md`, applies
   to research fetches too, not just the warehouse runtime). WebFetch itself got 403s on this
   host for the same reason and was abandoned in favor of `curl` with an identifying UA.
2. Grepped the repo for `daily-form-index`/`daily_form_index`/`form_index`/`daily-index` across
   `infra/scripts/deploy-aws-application.sh` and `edgar_warehouse/`, then read every hit's
   surrounding code in full (`warehouse_orchestrator.py`, `bronze_daily_index_extractors.py`,
   `bootstrap_fundamentals.py`, `command_scope.py`, `sec_calendar.py`).
3. Cross-checked "is this code live/used" against actual AWS state (`aws sts get-caller-identity`
   confirmed live credentials for account `690839588395`, the account this repo's `CLAUDE.md`
   names as current/active): `aws stepfunctions list-state-machines`,
   `list-executions` per state machine, and `aws events list-rules` /
   `list-targets-by-rule` for any EventBridge schedule wiring — not guessed from code alone.

---

## 1. SEC EDGAR daily-index: is there a JSON file, and what does it contain?

**Short answer: no.** Every per-day content file under `daily-index/` is either fixed-width text
(`.idx`) or an XML sitemap (`.xml`). The only JSON present at this path is EDGAR's
auto-generated **directory-listing** JSON, which enumerates the day's *filenames* (for browsing),
not filing records — it has no CIK/company/form/date/accession fields at all.

**Directory structure (fetched live):**
- `https://www.sec.gov/Archives/edgar/daily-index/index.json` — top-level listing of year
  directories. First entries: `1994`, `1995`, `1996`, ... (each `"type": "dir"`,
  `"last-modified": "11/24/2017 ..."` — the *directory entries* were catalogued in 2017, but that
  timestamp is just when S3 last touched the listing metadata, not filing history depth).
  Drilling in: `daily-index/1994/index.json` lists only `QTR3` and `QTR4` (no QTR1/QTR2 — `QTR1`
  returns `403 Forbidden`, gzip-encoded XML error body, confirmed via `curl -sD -`), and
  `daily-index/1994/QTR3/index.json`'s earliest file is `company.070194.idx` — **July 1, 1994**,
  not "1994" broadly. Also note the **old naming convention differs from the modern one**: 1994
  files use `company.MMDDYY.idx` (e.g. `070194` = July 1 1994), while 2026 files use
  `company.YYYYMMDD.idx` (e.g. `20260728`) — this repo's `build_daily_index_url()` (§2) only
  builds the modern `%Y%m%d` form, so it would not resolve pre-format-change dates as-is (not a
  problem for `daily_incremental`, which only ever targets recent dates, but worth knowing before
  reusing this URL builder for any historical backfill). **Confirmed history depth: 1994-07-01
  through present**, not further back.
- `https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/index.json` (fetched live, 95 items
  as of 2026-07-28) — lists one entry per day per file-type, e.g.:
  ```json
  {"last-modified":"07/28/2026 10:01:46 PM","name":"company.20260728.idx","type":"file","href":"company.20260728.idx","size":"865 KB"}
  ```
  Extensions present: `{idx, xml}` only — **zero `.json` content files**. Name prefixes present:
  `company`, `crawler`, `form`, `master`, `sitemap`.

**The four per-day index variants (all plaintext, not JSON), fetched live for 2026-07-28:**

| File | Format | Fields (in order) |
|---|---|---|
| `form.YYYYMMDD.idx` | Fixed-width columns | `Form Type`, `Company Name`, `CIK`, `Date Filed`, `File Name` |
| `company.YYYYMMDD.idx` | Fixed-width columns | `Company Name`, `Form Type`, `CIK`, `Date Filed`, `File Name` |
| `master.YYYYMMDD.idx` | Pipe-delimited | `CIK\|Company Name\|Form Type\|Date Filed\|File Name` (header line literally reads `CIK\|Company Name\|Form Type\|Date Filed\|File Name`) |
| `crawler.YYYYMMDD.idx` | Fixed-width columns | `Company Name`, `Form Type`, `CIK`, `Date Filed`, `URL` (fetched live: same company/form/CIK/date fields as `form.idx`/`company.idx`, but the last column is a full `http://www.sec.gov/.../...-index.htm` URL instead of a raw `edgar/data/...` path) |
| `sitemap.YYYYMMDD.xml` | XML sitemap | URLs only, for search-engine crawling — not a filing-record source |

Sample real row (`master.20260728.idx`, fetched live):
```
1000184|SAP SE|6-K|20260728|edgar/data/1000184/0001104659-26-087251.txt
```
`File Name` is a path to the filing's `.txt` submission wrapper
(`edgar/data/<cik>/<accession-no-dashes>.txt`); the accession number is derivable from it but is
not a separate column in any of the four variants — same as this repo's own extraction logic (see
§2).

**Magnitude, for scoping the follow-up decision ticket:** `master.20260728.idx` (fetched live,
one ordinary Tuesday) has **6,025 filing rows across 2,925 distinct CIKs** (`awk -F'|' '{print
$1}' | sort -u | wc -l`). Ticket 43's own background cites the tracked/active universe at
~26,300 CIKs. **2,925 / 26,300 ≈ 11% of the universe filed anything at all on this one sample
day** — i.e. if Stage 0 could be scoped to that day's `impacted_ciks` instead of the full
universe, the per-CIK submissions-refresh workload would drop by roughly an order of magnitude
for a single-day window (the actual saved wall-clock time also depends on
`_filter_ciks_to_universe`, `warehouse_orchestrator.py:1059`, which intersects `impacted_ciks`
with the tracked universe before use — some daily-index CIKs are for entities never onboarded
into this platform's tracked set at all, e.g. small Reg A/D filers, so the true post-intersection
count could be somewhat lower than 2,925). This is one sample day, not a distribution — worth a
multi-day sanity check before committing to a specific savings estimate in the decision ticket,
but it's directly the kind of number ticket 43 asked for ("instead of the full ~26,300 CIKs every
time").

**Cadence:** SEC's own file header states `Last Data Received: Jul 28, 2026` for the file whose
directory `last-modified` timestamp is **the same calendar day, ~10:01–10:06 PM ET** (confirmed
across every day in the QTR3 `index.json` listing — e.g. `07/28/2026 10:01:46 PM` for
`company.20260728.idx`). So a business day's index becomes available **that same evening around
10 PM ET**, not the next morning. This repo's own `expected_available_at()`
(`edgar_warehouse/domain/policy/sec_calendar.py:15-18`) instead gates on **next calendar day, 6:00
AM ET** — a conservative ~8-hour buffer past SEC's actual ~10 PM publish time, not wrong, just
later than strictly necessary. Not a bug worth fixing on its own, but relevant context if a future
change wants to tighten `daily_incremental`'s earliest-possible trigger time.

**Republish anomaly, found directly in the fetched data — a real safety concern for §3, not
hypothetical:** every day in the QTR3 `index.json` listing has a `last-modified` timestamp on the
**same calendar date** as the filing date, ~10 PM ET (e.g. `07/28/2026 10:01:46 PM` for
`company.20260728.idx`) — except one: **`company.20260710.idx`** (Friday, July 10 2026) shows
`"last-modified": "07/12/2026 11:11:10 AM"` — **modified the following Sunday morning**, roughly
37 hours after every other day's normal ~10 PM publish. SEC evidently republished/corrected that
day's index after its initial publish. Cross-referenced against this repo's own logic
(`_load_daily_index_for_date`, `warehouse_orchestrator.py:4140`): once a `business_date` is marked
`status == "succeeded"` in `sec_daily_index_checkpoint`, a subsequent call **without `--force`
returns the already-cached rows and does not re-fetch** — `if not force and existing and
existing.get("status") == "succeeded": ... return {... "network_fetches": 0 ...}`. If SEC
republishes a date's index with additional/corrected rows *after* this repo already marked that
date `succeeded` (as the July 10 anomaly shows can happen), those added rows — and any CIKs only
present in them — are never picked up on a later run unless `--force` is passed. This directly
matters for any narrowing keyed on `impacted_ciks`: it inherits this exact same gap, so a CIK
whose only activity that day appears in a late-republished index correction would be silently
missed by a narrowed Stage 0, independent of the administrative-drift risk below.

**Conclusion for ticket 43:** the "SEC daily changes file" the ticket's background flagged as
"a JSON file" does not exist as such — SEC only ever publishes this content as `.idx`/`.xml`.
What may have been meant is the auto-generated `index.json` directory listing itself (JSON, but a
file-name catalog, not filing data) or a JSON-shaped analog from elsewhere in the platform.
Either way, this repo's own pipeline (§2) already correctly targets the real content format
(`.idx`, via `build_daily_index_url`), not a nonexistent JSON endpoint — no fix needed there.

---

## 2. This repo's existing daily-form-index pipeline: real, working, and already CIK-scoped — but only inside `daily-incremental`, not in a separate state machine

**The parser is real code, not a stub, and it targets the correct real files.**
- `edgar_warehouse/infrastructure/sec_client.py:169-171` — `build_daily_index_url()` builds
  exactly the URL pattern confirmed live in §1:
  `{archive_url}/daily-index/{year}/QTR{q}/form.{date:%Y%m%d}.idx`.
- `edgar_warehouse/infrastructure/dataset_path_catalog.py:519-524` — `daily_index()` wraps that
  URL into a `CaptureSpec` with `source_name="daily_index"`.
- `edgar_warehouse/loaders/bronze_daily_index_extractors.py:9-72` —
  `stage_daily_index_filing_loader()` parses the `form.*.idx` fixed-width text with regex
  `_DAILY_IDX_FULL_PATTERN` (`form`, `company`, `cik`, `date`, `filename` capture groups),
  derives `accession_number` via `_ACCESSION_PATTERN` from the filename, and emits one row per
  filing with fields: `cik`, `company_name`, `form`, `filing_date`, `file_name`,
  `accession_number`, `filing_txt_url`, plus `business_date`/`source_year`/`source_quarter`
  bookkeeping. This is the exact "CIK, company name, form type, date filed, accession number,
  file name" shape ticket 43's background asked about — it already exists and is populated from
  the real SEC file, confirmed against the live `form.20260728.idx` sample in §1 (same column
  order: form, company, CIK, date, filename).
- Rows land in `stg_daily_index_filing` (schema: `edgar_warehouse/silver_store.py:326-346`) and a
  per-business-date checkpoint in `sec_daily_index_checkpoint`
  (`edgar_warehouse/silver_store.py:347-...`), read back via `db.get_daily_index_filings()`
  (`silver_store.py:2399-2407`) and `db.get_daily_index_checkpoint()` (`:2463-...`).

**Two things exist named "daily-form-index," and they are not the same thing operationally:**

1. **`daily-incremental` (CLI command, invoked as the `RunWarehouseTask` step inside the
   `daily_incremental` state machine)** — `edgar_warehouse/application/warehouse_orchestrator.py:1032-1108`.
   This command **internally** calls `_load_daily_index_for_date()`
   (`warehouse_orchestrator.py:4104-4256`) once per date in the `[business_date_start,
   business_date_end]` range, collects `impacted_ciks` (dedupe'd CIK list from that date's parsed
   daily-index rows, `:4229`) and `form_15_ciks` (CIKs that filed a Form 15 deregistration that
   day, via `_ciks_filing_form15`), then:
   - seeds newly-impacted CIKs into the tracked universe (`_seed_silver_tracking_status`, `:1057`),
   - demotes deregistered CIKs (`_demote_deregistered_ciks`, `:1058`),
   - **and only then fetches submissions/silver data for `impacted_ciks`** (windowed by
     `cik_offset`/`cik_limit`) via `_run_submissions_bronze_then_silver`, `:1074-1087`.

   **This is already exactly the narrow scoping ticket 43 is asking whether it's possible to
   build** — the actual filing-content fetch this command performs is bounded to "CIKs with a
   filing on the daily index for the date range," not the full universe. This is the *data
   ingestion* step, and it was never the bottleneck the ticket investigated.

2. **`load-daily-form-index-for-date` and `catch-up-daily-form-index`** — separate CLI commands
   (`edgar_warehouse/cli.py:145-150,331-357`) and separate deployed state machines
   (`edgartools-prod-load-daily-form-index-for-date`,
   `edgartools-prod-catch-up-daily-form-index`, both confirmed live via
   `aws stepfunctions list-state-machines --region us-east-1`). Both state machines are defined in
   `infra/scripts/deploy-aws-application.sh:3098` (the
   `for workflow in bootstrap_full targeted_resync full_reconcile load_daily_form_index_for_date
   catch_up_daily_form_index gold_refresh seed_universe` upsert loop) with their invoked CLI
   command expressions built at `:992-993`:
   `States.Array('load-daily-form-index-for-date', $.target_date, '--run-id', $$.Execution.Name)`
   and `States.Array('catch-up-daily-form-index', '--run-id', $$.Execution.Name)`. Note the
   asymmetry: `load-daily-form-index-for-date` requires an **operator-supplied `$.target_date`**
   in the Step Functions input (no default computed anywhere in the definition), while
   `catch-up-daily-form-index` needs **no date input at all** — it self-determines its start date
   from `db.get_last_successful_checkpoint_date()` (see below). That makes `catch-up` the one of
   the two that's actually usable as an unattended, no-parameter automated step; `load-...-for-date`
   would need something upstream to supply a date. Both call the **same**
   `_load_daily_index_for_date()` function as `daily-incremental` does
   (`warehouse_orchestrator.py:1110-1125` and `:4452-4494` respectively) — `catch-up` walks
   forward from `db.get_last_successful_checkpoint_date()` to a caller-given `end_date`
   (`:4461-4487`), backfilling missed daily-index checkpoints. **Neither of these two commands
   goes on to fetch any CIK's submissions/filing data** — they only populate
   `stg_daily_index_filing`/`sec_daily_index_checkpoint`, i.e. they are index-only backfill tools,
   distinct from `daily-incremental`'s combined index-parse-then-fetch behavior.

   **Live-state check (2026-07-29):**
   ```
   $ aws stepfunctions list-executions --state-machine-arn arn:...:edgartools-prod-catch-up-daily-form-index --max-items 10
   (empty — zero executions ever)
   $ aws stepfunctions list-executions --state-machine-arn arn:...:edgartools-prod-load-daily-form-index-for-date --max-items 10
   (empty — zero executions ever)
   $ aws events list-rules --region us-east-1
   only rule: StepFunctionsGetEventsForECSTaskRule (an internal CloudWatch Events→States wiring
   rule, ScheduleExpression: None) — no cron/rate rule targets any of these three state machines
   ```
   **These two standalone state machines are genuinely dead code in production as of this
   writing: deployed, but never once invoked, and with no EventBridge schedule wired up to invoke
   them automatically.** This matches `infra/scripts/deploy-aws-application.sh:2212`'s own comment
   ("daily_incremental had zero prod executions ever (confirmed via list-executions)") written at
   implementation time — that statement is stale as of today (`daily_incremental` now has exactly
   one execution, `daily-incremental-1785336584`, started 2026-07-29T10:49:46-04:00, **still
   RUNNING** at research time — the same execution ticket 43's own background section describes),
   but it was never updated for the other two, which really do still have zero executions.
   **`daily_incremental` itself also has no EventBridge schedule** — the one execution that exists
   was a manual/ad-hoc `start-execution`, not a recurring trigger. So "daily" is currently
   aspirational in the state-machine name only; nothing invokes any of these three on a cadence
   yet.

**Answer to "is it already wired to run before/alongside/unused":** none of the three options as
literally posed — `load-daily-form-index-for-date`/`catch-up-daily-form-index` are unused/orphaned
today (zero executions, no schedule); `daily-incremental`'s warehouse-task step does its own
internal daily-index parse (not a call to either of those two commands/state machines) and is
already correctly narrow at the filing-fetch level. The part of `daily_incremental` that is **not**
scoped by any of this is **Stage 0** (see §3), which runs as an entirely separate stage *before*
`RunWarehouseTask` and does not consume `impacted_ciks` at all.

**Important qualifier on "orphaned," revised after checking ordering (see §3): these two
commands are not just unused dead code — one of them (`catch-up-daily-form-index`) is exactly the
missing building block a narrowed Stage 0 would need**, because it is index-only (no CIK
data fetch) and self-parameterizing (no date input required), which is precisely the shape needed
to run *before* Stage 0 and hand it a fresh `impacted_ciks` list. It isn't dead code so much as an
already-built piece nobody has wired into `daily_incremental`'s definition yet.

---

## 3. Synthesis: does this unblock narrowing Stage 0, and what would be unsafe about it?

**Yes, with one structural correction: Stage 0 cannot simply "start consuming `impacted_ciks`" as
it stands today, because `impacted_ciks` does not exist yet at the point Stage 0 runs.** The
daily-index parse that produces `impacted_ciks` happens *inside* `RunWarehouseTask`
(`_load_daily_index_for_date`, called from the `command_name == "daily-incremental"` branch,
`warehouse_orchestrator.py:1039`) — and `Stage0CompanyIdentity` is the state **before**
`RunWarehouseTask` in the definition (`deploy-aws-application.sh:2227-2258`, `Next:
"RunWarehouseTask"` at `:2257`). A narrowed Stage 0 therefore needs a **new state ahead of Stage
0** that performs the daily-index parse first — and that state already exists as working,
deployed (if currently unscheduled) code: `catch-up-daily-form-index`
(`edgar_warehouse/application/warehouse_orchestrator.py:4452-4494`), which walks forward from
`db.get_last_successful_checkpoint_date()` to a caller-supplied `end_date`, calling the same
`_load_daily_index_for_date()` Stage 0 would need, with **no CIK data fetch attached** — exactly
an index-only pre-stage. Reframe §2's "orphaned" finding this way: it isn't just unused, it is the
piece a narrowed Stage 0 is missing.

**The other missing piece is a parameter, not new code — `bootstrap-fundamentals --mode
company-identity` already supports being handed an explicit CIK list instead of windowing the
full tracked universe.** `edgar_warehouse/application/commands/bootstrap_fundamentals.py:117-126`:
*"company-identity with an explicit `--cik-list` never reads the tracked universe from `db` ...
The windowed case (no `--cik-list`) still hydrates, since it resolves its CIK batch from
`db.get_tracked_ciks()`."* And `:149-154`: if neither `--cik-list` nor
`--cik-offset`/`--cik-limit`-resolvable tracking state is given, the command errors out — so
`--cik-list` is a first-class, already-implemented alternate path, not something that would need
to be added to `bootstrap_fundamentals.py` itself. The only real engineering gap is in
`deploy-aws-application.sh:2227-2258`: `Stage0CompanyIdentity`'s `per_window_company_identity`
state hardcodes `--cik-offset`/`--cik-limit` against a full-universe `compute-windows` output —
it never uses the `--cik-list` branch this same command already supports. A narrowed Stage 0 would
look like: new pre-stage (daily-index parse, reusing `catch-up-daily-form-index`'s logic) →
`bootstrap-fundamentals --mode company-identity --cik-list <impacted CIKs>` (chunked as needed) →
`RunWarehouseTask` as today (which would then re-derive `impacted_ciks` again for its own
filing-fetch scoping, or could be refactored to reuse the same list — a design choice for the
follow-up ticket, not settled by this research).

- `infra/scripts/deploy-aws-application.sh:2227-2258` builds `Stage0CompanyIdentity` as a
  `MaxConcurrency: 1` Distributed Map over **all** `compute-windows` output
  (`--window-size 500 --total-cik-limit 0`, i.e. no cap — the full tracked universe), calling
  `bootstrap-fundamentals --mode company-identity` per window, **before** `RunWarehouseTask` even
  runs. This stage's own `ItemReader` pulls from
  `warehouse/bronze/reference/cik_universe/runs/{execution}/cik_windows.jsonl` — a full-universe
  CIK list computed by `compute-windows`, entirely independent of any daily-index parse.
- The code's own comment block (`:2204-2226`) confirms ticket 43's hypothesis #2 outright:
  *"Reuses ticket 05's exact windowed capture shape (a strict, MaxConcurrency=1 Map calling
  `bootstrap-fundamentals --mode company-identity` over windows `ComputeWindows` just wrote),
  ahead of the existing `RunWarehouseTask`/MDM chain, so company data is current before the
  existing `mdm-run(--entity-type all)` resolves companies... daily_incremental had zero prod
  executions ever ... so this is a clean restructure, not a migration of live behavior."*
  In other words: Stage 0 was built by **copying `load_history`'s Stage 0 shape verbatim** (the
  same function, `write_load_history_definition`, builds an identical
  `per_window_company_identity` shape for `load_history` — see the "keep in sync" comment at
  `:2224-2226`), without narrowing it for a recurring/incremental cadence. This is a direct
  confirmation, not a guess: `load_history`'s Stage 0 exists to onboard a **brand-new** universe
  (where "process everyone" is correct by definition), and that shape was reused unmodified for
  `daily_incremental`, where it is not obviously correct.

- **What `bootstrap-fundamentals --mode company-identity` actually does per window**
  (`edgar_warehouse/application/commands/bootstrap_fundamentals.py:239-270`), and why that matters
  for a safe narrowing:
  1. `_sync_reference_data(...)` (`:246-253`) — fetches SEC's **global** bulk reference files,
     `company_tickers` and `company_tickers_exchange`
     (`warehouse_orchestrator.py:3765`, default `source_names`) — this is where **ticker/exchange
     changes** are captured, and it is **not** keyed to any individual CIK's filing activity that
     day. It is called once per window (53× across a full run) but is bronze-cache-backed
     (`_read_bronze_if_cached`, `warehouse_orchestrator.py:3779-3790`), so every call after the
     first in a run is a local cache hit, not a re-fetch — the redundancy is cheap, not a real cost
     driver.
  2. `_run_submissions_bronze_then_silver(..., ciks=cik_list, include_pagination=True, ...)`
     (`:258-267`) — this is the **expensive, per-CIK** part: a full paginated `submissions.json`
     fetch for **every CIK in the window**, regardless of whether that CIK filed anything that
     day. This is almost certainly the actual ~8-14-min/window cost driver ticket 43 measured,
     and it is the part with no relationship to the daily index at all in the current code.

- **Why full-universe scope isn't obviously required, but isn't zero-risk to narrow either:**
  - Form 15 deregistrations are **already** filing events that show up in the daily index and are
    **already** handled without touching Stage 0 —
    `_ciks_filing_form15`/`_demote_deregistered_ciks` run inside `daily-incremental`'s own
    `RunWarehouseTask` step (`warehouse_orchestrator.py:1052,1058`), not Stage 0. So
    deregistration is not, on its own, a reason Stage 0 needs the full universe.
  - Ticker/exchange changes are covered by the **global** `company_tickers`/
    `company_tickers_exchange` sync, which is **already CIK-independent** — it doesn't need Stage
    0's per-CIK windowing at all. If Stage 0 were narrowed to `impacted_ciks`, this global sync
    could simply be kept as a single, un-windowed step (run once, not 53×) rather than removed —
    it would keep working exactly as it does today.
  - **Two genuine residual risks, both real gaps a narrowed Stage 0 would introduce, neither
    mitigated anywhere in the existing code today:**
    1. **Per-CIK `submissions.json` drift with no accompanying same-day filing** — SEC can update
       a company's `former_name`/`address` fields in `submissions.json` (the source for
       `sec_company_former_name`/`sec_company_address`) via an administrative EDGAR correction
       that isn't necessarily reflected as a new dated filing in that day's daily index — e.g. a
       same-day filing under an old name where the name correction posts a day or two later, or a
       purely administrative CIK metadata fix with no filing event at all. A company whose
       `submissions.json` metadata changed with zero filing activity that day would not appear in
       `impacted_ciks` and would be silently skipped.
    2. **Daily-index republish after this repo's checkpoint already marked the date
       `succeeded`** — directly evidenced in §1's fetched data (`company.20260710.idx` republished
       ~37 hours after its normal publish window) combined with the no-`--force` cache
       short-circuit at `warehouse_orchestrator.py:4140`. Any CIK whose only activity for a date
       appears solely in a late correction to that date's index, fetched after this repo already
       checkpointed it `succeeded`, is invisible to `impacted_ciks` on every subsequent run unless
       something explicitly re-fetches with `--force`.

    Neither risk has an existing mitigation in this codebase — closing them would need either an
    accepted-risk decision, a periodic (e.g. weekly) full-universe sweep as a backstop, or some
    other detection signal not currently wired up.

**Bottom line for ticket 43:** the SEC daily-index (`.idx`, not JSON — see §1) already flows
through a real, working parser (§2) that `daily-incremental`'s own filing-fetch step already uses
to scope itself to `impacted_ciks`, and that parse produces roughly an order-of-magnitude fewer
CIKs than the full universe on a sample day (2,925 of ~26,300, §1's magnitude note). Stage 0
(`Stage0CompanyIdentity`) is the one piece that doesn't use this mechanism at all — it was built
as a verbatim copy of `load_history`'s full-universe Stage 0, per the code's own comment, not a
deliberate design decision that Stage 0 must see the whole universe every run. Narrowing it is not
a drop-in one-line change, though: because Stage 0 runs *before* the daily-index parse currently
happens, a narrower design needs a new pre-stage (the already-built, currently-unscheduled
`catch-up-daily-form-index` logic is the natural candidate) feeding CIKs into
`bootstrap-fundamentals --mode company-identity`'s existing-but-unused `--cik-list` path, with the
global ticker/exchange sync kept as-is but run once instead of per-window. That reuses only
already-tested code paths — no new parsing or fetch logic — but it would trade away same-day
coverage of two specific, evidenced gaps: non-filing-triggered `submissions.json` metadata drift,
and CIKs whose only activity appears in a late daily-index republish after this repo's checkpoint
already marked that date `succeeded`. Both are real, narrow gaps to explicitly accept or backstop
in the follow-up decision ticket, not reasons to leave Stage 0 unscoped by default.
