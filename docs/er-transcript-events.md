# ER transcript events (ERDP-04)

**Status:** phase-1 Gold Explore product
**Pilot sources:** `ir_website` (pointer-only), `firm_manual` (upload + pointer)
**Pilot universe (D6, locked):** `PILOT_CIKS = {320193}` (Apple only) — a small explicit list, **not** the full SEC universe and **not** a bulk third-party scrape
**Grade:** **Explore only** — not pure-SEC Agent-Grade Decision Features
**ADR:** [0001-agent-decision-surface-first.md](./adr/0001-agent-decision-surface-first.md)
**Spec:** `.scratch/er-data-plane/specs/ERDP-04-transcript-mvp.md`
**Code:** `edgar_warehouse.explore.transcript_events`

A durable **pointer** (+ optional platform-held copy) for one earnings call
or investor day event — **not** full NLP extraction of transcript content,
and not a replacement for the separate SEC filing text projection.

---

## 1. Product

| Layer | Name |
|-------|------|
| Gold export / SOURCE | `TRANSCRIPT_EVENTS` |
| dbt dynamic table | `EDGARTOOLS_GOLD.TRANSCRIPT_EVENTS` |
| Python builder | `build_transcript_events_table` / `build_transcript_events_table_from_rows` |
| Serving write | `write_transcript_events_to_serving_export` |
| Object path (platform copy) | `transcripts/cik={cik}/event_id={event_id}/transcript.txt` (`WarehousePathResolver.transcript_text_path`, A04.7) |

### Natural key

```text
(cik, event_id, source_system)
```

Unlike `CONSENSUS_ESTIMATES` / `GUIDANCE_FACTS` / `EARNINGS_CALENDAR`,
**`as_of` is not part of the natural key.** A pointer is revalidated in
place — re-registering the same event bumps `as_of` on the same row
(`event_key` is a deterministic hash of the natural key, and the
Snowflake load layer MERGEs on `event_key`) — it does not create a new
historical version. There is no `is_current` projection.

### Columns

`event_key`, `cik`, `ticker`, `company_key`, `event_id`, `event_type`,
`fiscal_year`, `fiscal_quarter`, `event_date`, `accession_number`,
`storage_uri`, `content_sha256`, `char_count`, `language`, `source_system`,
`source_url`, `as_of`, `ingested_at`.

| `event_type` | Meaning |
|---------------|---------|
| `earnings_call` | Quarterly earnings call |
| `investor_day` | Investor day / analyst day |
| `other` | Anything not covered above |

### Integrity (§5.3 of the spec)

1. `storage_uri` non-null and non-empty (**hard** — rejected otherwise).
2. If `storage_uri` starts with `s3://`, `content_sha256` **should** be set
   (**soft** — logs a warning, does not reject; a pointer-only re-registration
   of an externally-uploaded object is still valid).
3. If `https://` only, `char_count`/`content_sha256` are optional.
4. No market fields.

No price / mcap / PE / EV columns (ERDP-06).

---

## 2. Load paths

### 2.1 ir_website — pointer-only (A04.6)

```python
from datetime import date
from edgar_warehouse.explore.transcript_events import register_ir_pointer

row = register_ir_pointer(
    cik=320193,
    ticker="AAPL",
    event_date=date(2026, 7, 31),
    source_url="https://investor.apple.com/fy2026q3-call",
)
```

No bytes are fetched or stored. `event_id` is derived deterministically from
`(cik, event_date, event_type, source_url)`, so re-registering the same URL
is idempotent — same `event_key`, `as_of` just advances.

### 2.2 firm_manual — platform-held copy (A04.5)

```python
from datetime import date
from edgar_warehouse.explore.transcript_events import store_transcript_text
from edgar_warehouse.infrastructure.object_storage import StorageLocation

storage_root = StorageLocation(root="s3://edgartools-dev-warehouse/warehouse")
row = store_transcript_text(
    cik=320193,
    ticker="AAPL",
    event_date=date(2026, 7, 31),
    text=call_transcript_text,
    storage_root=storage_root,
    source_system="firm_manual",
)
```

Computes `content_sha256` (SHA-256 of the UTF-8 text) and `char_count`,
writes to the warehouse object store at the path above, and returns the
gold pointer row with `storage_uri` set to the written object's location.

### 2.3 firm_manual — metadata-only CSV (already-uploaded object)

```csv
cik,event_id,event_type,event_date,storage_uri
320193,fy2026q3,earnings_call,2026-07-31,s3://edgartools-dev-warehouse/warehouse/transcripts/cik=320193/event_id=fy2026q3/transcript.txt
```

```python
from edgar_warehouse.explore.transcript_events import load_firm_manual_csv

rows = load_firm_manual_csv("pilot_transcripts.csv")
```

Use when ops has already dropped the `.txt` to S3 out-of-band and only
needs to publish the pointer row; for uploading text through this module,
use `store_transcript_text` instead (§2.2).

---

## 3. Query patterns

### Latest earnings call for a CIK

```sql
SELECT *
FROM EDGARTOOLS_GOLD.TRANSCRIPT_EVENTS
WHERE cik = ? AND event_type = 'earnings_call'
QUALIFY ROW_NUMBER() OVER (ORDER BY event_date DESC, as_of DESC) = 1;
```

### Agent usage (A04.3 — no web search when a URI is present)

1. Query gold for `storage_uri`.
2. If `s3://`: warehouse object-read API (`edgar_warehouse.infrastructure.object_storage.read_bytes`) or a pre-signed URL.
3. If `https://`: fetch with rate limiting + cache.
4. Feed text into the `earnings-analysis` skill's context.

Explore only; not a Decision Bundle section in phase-1 (A04.4 — no
requirement to put transcript content into pure-SEC feature vectors).

---

## 4. Acceptance

| ID | Criterion |
|----|-----------|
| **A04.1** | Sample event: gold row with `event_date` + resolvable `storage_uri` |
| **A04.2** | Fetch yields non-empty text (s3 read or HTTP 200) — exercised manually for the pilot; no automated live-fetch test in CI |
| **A04.3** | Doc path for earnings-analysis without web search when URI present (§3) |
| **A04.4** | No requirement to put transcript content into pure-SEC features |
| **A04.5** | firm_manual: upload + publish for 1 CIK (`store_transcript_text`) |
| **A04.6** | ir_website: pointer-only row for 1 CIK with a live URL (`register_ir_pointer`) |
| **A04.7** | Object path documented in path catalog — `transcripts.text.path` in `warehouse_paths.properties` |

---

## 5. Related

- [er-consensus-estimates.md](./er-consensus-estimates.md) — ERDP-01
- [er-guidance-facts.md](./er-guidance-facts.md) — ERDP-02
- [er-earnings-calendar.md](./er-earnings-calendar.md) — ERDP-03
- Reactive SEC filing text: separate silver text path (`text.path` in `warehouse_paths.properties`), unrelated to this product
