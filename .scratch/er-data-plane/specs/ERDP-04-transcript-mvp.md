# ERDP-04 — Transcript MVP (Detailed Product Spec)

| Field | Value |
|-------|--------|
| **ID** | ERDP-04 |
| **Name** | Transcript MVP |
| **Status** | Spec ready for design/build planning (not implemented) |
| **Pilot source_system** | **`ir_website`** + **`firm_manual`** (small pilot CIK list; not full-universe free API) |
| **Milestone** | ER data plane phase-1 |
| **REQUIREMENTS** | `.planning/workstreams/er-data-plane/REQUIREMENTS.md` (ERDP-04-*) |
| **Parent plan** | `.scratch/er-data-plane/spec.md` |
| **Schema sketch** | `.scratch/er-data-plane/assets/erdp-01-04-schema-sketches.md` § ERDP-04 |
| **Free sources research** | `.scratch/er-data-plane/assets/free-data-sources-erdp-01-04.md` |
| **Consumers** | `earnings-analysis` (primary), `earnings-preview` / `morning-note` (secondary) |
| **Layer** | **Object store** (text) + **Gold pointer table**; optional MDM keys; **not** graph; **not** Bundle phase-1; **not** pure-SEC features |

---

## 1. Problem statement

Post-print equity research needs **earnings call transcripts** (or equivalent prepared remarks + Q&A) to:

- Attribute management commentary in **earnings-analysis**  
- Avoid relying on training-cutoff or ad-hoc web search when a controlled copy exists  

Platform today: filings text projection is partial/backfill; **no** first-class transcript product.

**ERDP-04 MVP** = durable **pointer** (+ optional stored text) for a call event — **not** full NLP extraction of KPIs from transcripts.

---

## 2. Goals and non-goals

### Goals

1. Gold table of **transcript events** with stable `event_id`, CIK, event_date, type.  
2. **Resolvable** `storage_uri` (S3 warehouse path or https URL).  
3. Optional **platform-held copy** of text with integrity (`content_sha256`, `char_count`).  
4. Link optional `accession_number` (related 8-K).  
5. Provider-agnostic + firm_manual + IR website.  
6. Explore-only; bulk text not in pure-SEC feature vectors.

### Non-goals

| Out | Notes |
|-----|--------|
| Full-universe free automated scrape of Seeking Alpha | ToS / legal risk |
| Speaker diarization NLP product | Future |
| Embedding search index | Future |
| Agent-Grade Bundle section in phase-1 | Optional later |
| Replacing SEC filing text product | Separate silver text path remains |

---

## 3. User stories

1. **As** `earnings-analysis`, open the Q3 call text for CIK after print without web search.  
2. **As** ops, register an IR URL for a pilot name without storing bytes.  
3. **As** ops, upload a firm-provided `.txt` for a call into S3 and publish gold pointer.  
4. **As** compliance, prove SHA256 of stored text for audit.

---

## 4. Data product definition

### 4.1 Two-part product

```text
TRANSCRIPT_EVENTS (gold pointer metadata)
        │
        ├── storage_uri → s3://…/transcripts/…/transcript.txt   [optional platform copy]
        └── storage_uri → https://ir.example.com/...            [pointer-only OK for MVP]
```

### 4.2 Event model

One event ≈ one earnings call (or investor day) for one issuer.

**Natural key:**

```text
(cik, event_id, source_system)
```

`event_id` rules:

| Source | event_id suggestion |
|--------|---------------------|
| firm_manual | firm-supplied id or `fy{year}q{q}` |
| Provider | provider’s id |
| IR only | hash(`cik|event_date|event_type|url`) |

### 4.3 Object store layout (platform copy)

```text
{warehouse_root}/transcripts/
  cik={cik}/
    event_id={event_id}/
      transcript.txt          # or .jsonl diarized
      meta.json               # optional: title, speakers, language
```

Path templates should be added to warehouse path catalog at build time (not done in this planning doc).

---

## 5. Logical schema (normative)

### 5.1 Gold pointer table

| Layer | Name |
|-------|------|
| Silver | `ext_transcript_event` |
| Gold | `TRANSCRIPT_EVENTS` |
| dbt | `EDGARTOOLS_GOLD.TRANSCRIPT_EVENTS` |

### 5.2 Columns

| Column | Type | Null | Description |
|--------|------|:----:|-------------|
| `event_key` | int64 | N | Surrogate |
| `cik` | int64 | N | |
| `ticker` | string | Y | |
| `company_key` | int64 | Y | |
| `event_id` | string | N | Stable id |
| `event_type` | string | N | `earnings_call` \| `investor_day` \| `other` |
| `fiscal_year` | int32 | Y | |
| `fiscal_quarter` | int32 | Y | 1–4 or 0 |
| `event_date` | date | N | Call / transcript date |
| `accession_number` | string | Y | Related 8-K if known |
| `storage_uri` | string | N | s3:// or https:// |
| `content_sha256` | string | Y | Required if platform-held bytes |
| `char_count` | int64 | Y | |
| `language` | string | Y | default `en` |
| `source_system` | string | N | `ir_website` \| `firm_manual` \| `fmp` \| `other` |
| `source_url` | string | Y | Canonical public URL |
| `as_of` | date | N | When pointer verified |
| `ingested_at` | timestamp | N | |

### 5.3 Integrity

1. `storage_uri` non-null and non-empty.  
2. If URI scheme is `s3` (or warehouse path), `content_sha256` **should** be set.  
3. If `https` only, char_count/sha optional; A04.2 uses HTTP fetch in test.  
4. No market fields.

---

## 6. Source strategies

### 6.1 Free / legitimate pilot (recommended)

| source_system | How |
|---------------|-----|
| `ir_website` | Gold pointer to official IR transcript URL; optional download to S3 |
| `firm_manual` | Ops drops file to S3 + metadata CSV |

### 6.2 Freemium APIs

| Source | Use |
|--------|-----|
| FMP / others | Prototype only; check commercial redistribution ToS |

### 6.3 Avoid as default bulk free path

Seeking Alpha scrape for gold warehouse — **high ToS/legal risk**.

### 6.4 Pipeline sketch

```text
A) Pointer-only:
   firm/IR list → validate URL → TRANSCRIPT_EVENTS

B) Store copy:
   fetch or upload → write object store → sha256 → TRANSCRIPT_EVENTS.storage_uri
```

Universe: start with **pilot CIK list** (N small), not full SEC universe.

---

## 7. Query patterns

### 7.1 Latest earnings call for CIK

```sql
SELECT *
FROM EDGARTOOLS_GOLD.TRANSCRIPT_EVENTS
WHERE cik = ? AND event_type = 'earnings_call'
QUALIFY ROW_NUMBER() OVER (ORDER BY event_date DESC, as_of DESC) = 1;
```

### 7.2 Agent usage

1. Query gold for `storage_uri`  
2. If s3: warehouse read API / pre-signed URL  
3. If https: fetch with rate limit + cache  
4. Feed text into earnings-analysis skill context  

Explore only; not Decision Bundle section in phase-1.

---

## 8. Acceptance criteria

| ID | Criterion |
|----|-----------|
| **A04.1** | Sample event: gold row with `event_date` + resolvable `storage_uri`. |
| **A04.2** | Fetch yields non-empty text (s3 or HTTP 200). |
| **A04.3** | Doc path for earnings-analysis without web search when URI present. |
| **A04.4** | No requirement to put transcript into pure-SEC features. |
| **A04.5** | firm_manual: upload + publish for 1 CIK. |
| **A04.6** | ir_website: pointer-only row for 1 CIK with live URL. |
| **A04.7** | Object path documented in path catalog (at build). |

---

## 9. REQUIREMENTS checklist

- [ ] ERDP-04-01…05  
- [ ] A04.5–A04.7  
- [ ] Path catalog entry for transcripts/  
- [ ] Pilot universe definition  

---

## 10. Open design decisions

| # | Decision | Default |
|---|----------|---------|
| D1 | Pointer-only vs store-first for pilot | **Both allowed**; pilot may be pointer-only |
| D2 | Text format | plain `.txt` UTF-8 first; jsonl later |
| D3 | Link to calendar | Optional join on cik+FY+FQ to ERDP-03 |
| D4 | Max char retention | No hard limit phase-1; monitor cost |
| D5 | Redaction | None phase-1 (public transcripts only) |
| D6 | Pilot sources | **Locked: `ir_website` + `firm_manual` only** (no Seeking Alpha bulk scrape) |

### 10.1 Pilot source lock (2026-07-25)

| Role | source_system | Notes |
|------|---------------|--------|
| Primary | `ir_website` | Official IR HTTPS `storage_uri` / `source_url`; optional download to S3 |
| Primary | `firm_manual` | Ops drops `.txt` + metadata for demo CIKs |
| Universe | — | **Small pilot CIK list**, not full SEC universe |
| Out | Seeking Alpha bulk scrape, free commercial bulk APIs as default | ToS / coverage risk |
| Optional later | `fmp` / paid transcript APIs | Schema already allows `source_system` |

---

## 11. Risks

| Risk | Mitigation |
|------|------------|
| IR URL rot | as_of revalidation job; firm S3 copy for key names |
| ToS on third-party APIs | Prefer IR + firm_manual for gold |
| Huge text in SQL | Keep body out of Snowflake table; pointer only |
| Incomplete coverage | MVP = pilot list, not 100% universe |

---

## 12. Traceability

Parent plan, REQs, free-data note, ER skill I/O (`earnings-analysis`), ADR 0001, filing text projection (related but separate).

---

*Spec version 1.0 — planning; not implemented.*
