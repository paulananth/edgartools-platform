# Phase-1 schema sketches + acceptance criteria (prototype)

**Status:** **accepted** (ticket 06) — frozen for REQUIREMENTS generation  
**Layer:** Gold Explore (not Agent-Grade pure-SEC features)  
**Naming:** warehouse export style `SCREAMING_SNAKE`; dbt may publish as `EDGARTOOLS_GOLD.<name>`

Grain and keys align with existing gold patterns: `cik`, optional `company_key`, ISO dates, `ingested_at`, `source_*` lineage.

---

## ERDP-01 — Consensus estimates

### Proposed table: `CONSENSUS_ESTIMATE` / `EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES`

| Column | Type | Nullable | Notes |
|--------|------|:--------:|-------|
| `fact_key` | int64 | N | Deterministic hash of natural key |
| `cik` | int64 | N | Issuer |
| `ticker` | string | Y | Display / join aid |
| `company_key` | int64 | Y | Optional dim link |
| `metric` | string | N | Controlled vocab: `revenue`, `eps_diluted`, `ebitda`, `net_income`, `gross_profit`, … |
| `period_type` | string | N | `annual` \| `quarterly` \| `ntm` \| `ltm` |
| `fiscal_year` | int32 | Y | Required when period is FY/FQ |
| `fiscal_quarter` | int32 | Y | 1–4 when quarterly |
| `period_end` | date | Y | When known |
| `estimate_value` | float64 | N | Consensus level (define units in `unit`) |
| `unit` | string | N | `USD`, `USD_millions`, `per_share`, … |
| `statistic` | string | N | `mean` \| `median` \| `high` \| `low` \| `stdev` \| `n_analysts` |
| `as_of` | date | N | Consensus snapshot date (**mandatory for ER beat/miss**) |
| `source_system` | string | N | e.g. `factset`, `bloomberg`, `cap_iq`, `firm_feed` |
| `source_ref` | string | Y | Provider row id / file key |
| `currency` | string | Y | ISO 4217 when monetary |
| `ingested_at` | timestamp | N | Load time |

**Natural key (recommended):**  
`(cik, metric, period_type, fiscal_year, fiscal_quarter, statistic, as_of, source_system)`  
with null fiscal_quarter encoded as `0` for annual.

**Not in this table:** price targets, ratings (External / deferred).

### Acceptance criteria (ERDP-01)

| ID | Criterion |
|----|-----------|
| A01.1 | For a test CIK with known Street history, query returns ≥1 row for `metric=eps_diluted` and `metric=revenue` for the latest completed fiscal quarter with non-null `as_of`. |
| A01.2 | Two snapshots on different `as_of` dates for the same period are both retained (no silent overwrite of history). |
| A01.3 | Agent documentation states this table is **Explore / not Agent-Grade pure-SEC**. |
| A01.4 | Join to identity: every row’s `cik` exists in `COMPANY` or `TICKER_REFERENCE` for tracked universe sample. |
| A01.5 | ER skill path: `earnings-preview` and `earnings-analysis` can compute beat/miss when paired with `EARNINGS_RELEASES` or actuals using same period keys + `as_of` ≤ print date. |

---

## ERDP-02 — Guidance facts

### Proposed table: `GUIDANCE_FACT` / `EDGARTOOLS_GOLD.GUIDANCE_FACTS`

| Column | Type | Nullable | Notes |
|--------|------|:--------:|-------|
| `fact_key` | int64 | N | |
| `cik` | int64 | N | |
| `ticker` | string | Y | |
| `company_key` | int64 | Y | |
| `accession_number` | string | Y | Source filing when from 8-K/10-Q |
| `metric` | string | N | `revenue`, `eps_diluted`, `ebitda`, … |
| `period_type` | string | N | `annual` \| `quarterly` \| `range_fy` |
| `fiscal_year` | int32 | Y | Guided period |
| `fiscal_quarter` | int32 | Y | |
| `period_end` | date | Y | |
| `value_low` | float64 | Y | Range low |
| `value_mid` | float64 | Y | Point or midpoint |
| `value_high` | float64 | Y | Range high |
| `unit` | string | N | |
| `is_non_gaap` | bool | N | default false |
| `as_of` | date | N | Date guidance was given (often filing_date) |
| `source_system` | string | N | `sec_8k` \| `sec_10q` \| `sec_10k` \| `other` |
| `parser_version` | string | Y | When platform-parsed |
| `ingested_at` | timestamp | N | |

**Natural key (recommended):**  
`(cik, metric, fiscal_year, fiscal_quarter, as_of, accession_number, is_non_gaap)`  

**Relation to existing:** Extends beyond `EARNINGS_RELEASES.has_guidance` boolean; does not remove that flag.

### Acceptance criteria (ERDP-02)

| ID | Criterion |
|----|-----------|
| A02.1 | For a sample 8-K known to contain numeric guidance, ≥1 row with at least one of low/mid/high non-null and `accession_number` set. |
| A02.2 | Rows are joinable to `EARNINGS_RELEASES` or `FILING_DETAIL` on `(cik, accession_number)` when accession present. |
| A02.3 | `model-update` can show prior guide vs new actual using guidance rows with `as_of` before print and period keys matching the quarter. |
| A02.4 | Documented as Gold Explore; not injected into pure-SEC `subject_features`. |

---

## ERDP-03 — Earnings calendar

### Proposed table: `EARNINGS_CALENDAR` / `EDGARTOOLS_GOLD.EARNINGS_CALENDAR`

| Column | Type | Nullable | Notes |
|--------|------|:--------:|-------|
| `fact_key` | int64 | N | |
| `cik` | int64 | N | |
| `ticker` | string | Y | |
| `company_key` | int64 | Y | |
| `fiscal_year` | int32 | N | |
| `fiscal_quarter` | int32 | N | 1–4 |
| `expected_date` | date | N | Calendar date of print |
| `expected_time` | string | Y | `HH:MM` UTC or local with `timezone` |
| `timezone` | string | Y | e.g. `America/New_York` |
| `session` | string | N | `pre_market` \| `after_close` \| `during_session` \| `unknown` |
| `status` | string | N | `estimated` \| `confirmed` \| `reported` \| `cancelled` |
| `period_end` | date | Y | Fiscal period end |
| `source_system` | string | N | Provider or `firm_manual` |
| `source_ref` | string | Y | |
| `as_of` | date | N | When this calendar row was last verified |
| `ingested_at` | timestamp | N | |

**Natural key (recommended):**  
`(cik, fiscal_year, fiscal_quarter, source_system)` with latest `as_of` winning for “current” view (history optional via snapshot table later).

**Not the same as:** `filing_date` on 8-K (reactive). Calendar is **forward-looking**.

### Acceptance criteria (ERDP-03)

| ID | Criterion |
|----|-----------|
| A03.1 | For a coverage universe sample (N≥10 tickers), ≥80% have a row for the next expected quarter with `expected_date` ≥ today or `status=reported` for the just-completed quarter. |
| A03.2 | `session` is non-null for confirmed rows (allow `unknown` only for `estimated`). |
| A03.3 | `catalyst-calendar` skill can list next 2 weeks of earnings from this table alone for tracked CIKs. |
| A03.4 | Explore-only; not pure-SEC Agent-Grade features. |

---

## ERDP-04 — Transcript MVP

### Object store

| Path pattern (illustrative) | Content |
|----------------------------|---------|
| `transcripts/cik={cik}/event_id={event_id}/transcript.txt` (or `.jsonl`) | Full text or diarized turns |
| Optional | `meta.json` sibling |

### Proposed gold pointer table: `TRANSCRIPT_EVENT` / `EDGARTOOLS_GOLD.TRANSCRIPT_EVENTS`

| Column | Type | Nullable | Notes |
|--------|------|:--------:|-------|
| `event_key` | int64 | N | |
| `cik` | int64 | N | |
| `ticker` | string | Y | |
| `company_key` | int64 | Y | |
| `event_id` | string | N | Stable id (provider or hash) |
| `event_type` | string | N | `earnings_call` \| `investor_day` \| `other` |
| `fiscal_year` | int32 | Y | |
| `fiscal_quarter` | int32 | Y | |
| `event_date` | date | N | Call date |
| `accession_number` | string | Y | Related 8-K if any |
| `storage_uri` | string | N | s3://… or warehouse path to text |
| `content_sha256` | string | Y | Integrity |
| `char_count` | int64 | Y | |
| `source_system` | string | N | |
| `source_url` | string | Y | Public URL if any |
| `as_of` | date | N | When pointer confirmed |
| `ingested_at` | timestamp | N | |

**Natural key:** `(cik, event_id, source_system)`

**Phase-1 MVP:** pointer + optional stored text; **not** full NLP entity extraction.

### Acceptance criteria (ERDP-04)

| ID | Criterion |
|----|-----------|
| A04.1 | For a sample earnings event, gold row exists with resolvable `storage_uri` and `event_date`. |
| A04.2 | Fetching `storage_uri` returns non-empty text (or documented external URL with HTTP 200 in test env). |
| A04.3 | `earnings-analysis` can cite call date and open transcript body without web search when URI is present. |
| A04.4 | No requirement that transcript content enter pure-SEC feature vectors. |

---

## ERDP-05 — Existing surface (acceptance add-on)

Already drafted in [erdp-05-existing-surface-read-map.md](./erdp-05-existing-surface-read-map.md).

| ID | Criterion |
|----|-----------|
| A05.1 | Spec §5 + asset list every Partial product from coverage matrix footnotes F1–F12. |
| A05.2 | Agent-Grade vs Explore rules documented (watermark / abstain). |
| A05.3 | Partial → Covered only when each product has a named acceptance query (follow-up hardening; not blocking schema freeze for 01–04). |

---

## ERDP-06 — Boundary (locked ticket 03)

| ID | Criterion |
|----|-----------|
| A06.1 | No new ERDP-01…04 column set includes price, mcap, PE, EV. |
| A06.2 | Serving docs state Agent-Grade features remain pure-SEC. |
| A06.3 | Market join documented as External (phase-1) with join keys ticker/CIK + as_of. |

---

## Source policy stubs (for REQUIREMENTS.md — still fog on vendor)

| Product | Source policy (phase-1 requirement language) |
|---------|-----------------------------------------------|
| Consensus | **Must** define at least one `source_system`; provider choice is implementation (vendor API, firm file drop, or multi-source). Schema is provider-agnostic. |
| Guidance | Prefer platform parse from SEC 8-K/10-Q HTML when present; allow firm override rows with `source_system=firm_manual`. |
| Calendar | Provider-agnostic; firm_manual allowed; must support `estimated` vs `confirmed`. |
| Transcript | Provider-agnostic pointer; optional platform-held copy in object store. |

---

## Non-goals in these schemas

- Peer comps packs  
- Street ratings / price targets  
- Daily bars / options  
- Full segment revenue mart  
- Neo4j edges for estimates  

---

## Freeze checklist (ticket 06)

- [ ] Human accepts schema sketches (or lists column changes)  
- [ ] Human accepts acceptance IDs A01.*–A06.*  
- [ ] Promote into `spec.md` §7 and mark ticket 06 resolved  
- [ ] Unblock ticket 07 → `.planning/workstreams/er-data-plane/REQUIREMENTS.md`  
