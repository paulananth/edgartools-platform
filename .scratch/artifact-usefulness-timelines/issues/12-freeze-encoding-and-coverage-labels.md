# Freeze encoding and coverage labels

Type: grilling
Status: resolved
Blocked by: 08, 09, 10, 11
Blocks: 13
Assignee: grok-session

## Question

How must the frozen candidate inventory encode **per-document-type** windows
(`coverage_by_document_type`) and how must Decision Contract / SiS expose
coverage so agents never infer full-history claims?

## Exit criteria

- Freeze metadata shape accepted.
- Contract/SiS labeling rule accepted.
- Rebuild-freeze required before GO under new windows: yes/no.

## Answer

**Locked 2026-07-18 (wayfinder grill Q1–Q5).**

### Freeze identity shape

| Field | Role |
| --- | --- |
| **`coverage_by_document_type`** | **Product truth** — per-family agent windows for Ticket 20 |
| **Top-level `coverage_start`** | **Quarter-index floor / inventory identity only** = `min(per-type absolute starts)` for families in this freeze. **Not** “all forms load from here.” |
| **`watermark`** | Release Data Watermark `W` (end of all windows) |

### Per-type product windows (must match locked agent windows)

```text
coverage_by_document_type:
  thirteenf:   { start: max(W-3y, 2013-05-20), end: W }
  proxy:       { start: W-5y, end: W, baseline: "latest_in_band_only" }
  item_502_8k: { start: W-2y, end: W }
# Form 3/4/5 omitted — not Ticket 20 freeze (silver-once ownership path)
```

Top-level `coverage_start` = min of the absolute start dates above (typically 13F start when W is recent).

### Candidate membership

A row is in `candidates[]` **iff**:

1. form family ∈ Ticket 20 set (`13F-HR`/`13F-HR/A`, proxy family, `8-K`/`8-K/A` Item 5.02 or ambiguous), **and**
2. `filing_date` ∈ that family’s agent window.

Out-of-window rows **never** enter the list (no “include then mark N/A for GO”).

### Contract / SiS exposure

- **Machine-readable:** Decision Contract carries `coverage_by_document_type` (or equivalent section-level coverage start/end).
- **Human labels required** on SiS Agent View (per-type phrases).
- **Forbidden:** implying “complete history since 2013” for all relationship forms.
- **Explore:** wider archives allowed only with **explicit non-agent** labels.

Exact GO/PASS phrase library → ticket **13**.

### Rebuild before GO

**Yes — full rebuild required.** Live full-window freeze (e.g. 2013-era ~529k candidates, old fingerprint) is **invalid** for agent-grade Ticket 20 GO under these windows. New freeze must include:

- per-type membership filtering,
- `coverage_by_document_type` on the manifest,
- new inventory fingerprint (must hash coverage + candidates identity).

Post-filter of the old freeze without a new fingerprint is **not** GO.

## Grill log

| # | Topic | Decision |
| --- | --- | --- |
| 1 | Freeze identity shape | **`coverage_by_document_type` is product truth** + top-level `coverage_start` kept as **min-of-types / quarter-index floor only** |
| 2 | Top-level `coverage_start` value | **`min(per-type absolute starts)`** for families in the freeze; not fixed 2013 |
| 3 | Candidate membership | **In freeze iff** form ∈ T20 set **and** `filing_date` ∈ that family’s agent window |
| 4 | Contract / SiS exposure | **Machine-readable + required human SiS labels**; forbid universal “complete since 2013”; Explore = non-agent labels |
| 5 | Rebuild before GO | **Yes — full rebuild required** (new fingerprint). No post-filter-only GO |
