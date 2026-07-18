# Relationship source coverage by document type

## Decision

Ticket 20 / required relationship bulk-load **must not use a single global
“load every form since 2013” window for every document class.**

Coverage is **document-type (form-family) specific**. Each form family has its
own **lookback start** relative to the Release Data Watermark (or an absolute
floor when a regulatory format break requires it). The freeze inventory, bulk
load, ledger, and dashboard copy must honor the per-type window for that type
and **must not imply** history outside that type’s declared window.

This supersedes treating `DEFAULT_COVERAGE_START = 2013-05-20` as the universal
start for **all** relationship source forms. That date remains the **13F XML
floor only**, not an 8-K or proxy load mandate.

**Status:** Release Data / Release Owner **product decision** (2026-07-18).  
**Implementation:** inventory builder must filter candidates **per form family**
before StrictBatchSilver; a single global `--coverage-start` is insufficient.

## Watermark

All windows end at the **Release Data Watermark** `W` (inclusive), unless a
row is superseded earlier by amendment semantics.

## Required windows (initial GO policy)

| Document family | Forms | Lookback start | Why this window |
| --- | --- | --- | --- |
| **Institutional holdings (13F)** | `13F-HR`, `13F-HR/A` | **`max(W − 3 years, 2013-05-20)`** for **agent-useful first GO**; hard floor **`2013-05-20`** (cannot claim pre-XML 13F). Full XML-era archive is optional Explore backfill, not first agent GO. | Agent needs current holdings + short change context; 3y confirmed in product grill. XML floor is format, not “load everything since 2013 for agents.” See [agent-and-research-source-relevance-windows.md](./agent-and-research-source-relevance-windows.md). |
| **Proxy compensation / employment baseline** | `DEF 14A`, `DEF 14A/A`, `DEFA14A`, `PRE 14A` | Filing date ≥ **`W − 5 years`** only; baseline = latest proxy in that band (if any). **No** pre–W−5y baseline exception. | Wayfinder lock 2026-07-18. |
| **Item 5.02 employment events (8-K)** | `8-K`, `8-K/A` with Item 5.02 **or** missing/ambiguous items | Filing date ≥ **`W − 2 years`** | Wayfinder lock 2026-07-18: **two years** for agent employment events; older 5.02 Explore-only. |
| **Unrelated 8-K** (items prove no 5.02) | `8-K`, `8-K/A` | **Out of scope** for bulk download | Metadata `not_applicable`; do not treat earnings 8-Ks as employment candidates. |

Notes:

1. **Document-by-document** means: a filing’s eligibility is decided from its
   **form family + filing_date (+ items for 8-K)**, not from “any document for
   this CIK since 2013.”
2. **8-K two years** applies to **artifact-required** Item 5.02 / ambiguous
   8-Ks. It does **not** shorten 13F or proxy windows.
3. **Current-at-watermark** for `EMPLOYED_BY` requires:
   - latest applicable definitive proxy with filing date in **`[W−5y, W]`**
     (if none exists, baseline is missing — not filled by older proxies), and  
   - relevant Item 5.02 8-Ks with filing date in **`[W−2y, W]`** after that
     baseline (and in window).
4. **Never** load proxies older than `W − 5 years` for first agent GO (product
   lock); Expand only via Explore backfill if desired.
5. **Dashboard / generation** language must state each type’s coverage start so
   users never read “complete history since 2013” for 8-K employment events.

## Why not one global 2013 start for everything

| Concern | Global 2013 | Per-document windows |
| --- | --- | --- |
| 13F XML correctness | Needed | Keep 2013 floor for 13F only |
| Bulk-load cost | Dominated by 13F + years of 8-K noise | 8-K cut to 2y removes large low-value volume |
| Product claim | Over-claims 8-K history | Matches how employment is used (recent events + proxy) |
| Ticket 20 GO | Single huge freeze | Freeze still fail-closed **inside each type’s window** |

## Freeze / inventory requirements

**Wayfinder ticket 12 locked 2026-07-18.**

| Field | Role |
| --- | --- |
| **`coverage_by_document_type`** | **Product truth** — per-family agent windows |
| **Top-level `coverage_start`** | **Index floor only** = `min(per-type absolute starts)` for families in this freeze. **Not** “all forms load from here.” |
| **`watermark`** | End of all windows (`W`) |

```text
coverage_start: <min of type starts>   # quarter-index floor / inventory identity
watermark: W
coverage_by_document_type:
  thirteenf:   { start: max(W-3y, 2013-05-20), end: W }
  proxy:       { start: W-5y, end: W, baseline: "latest_in_band_only" }
  item_502_8k: { start: W-2y, end: W }
# Form 3/4/5 omitted — not Ticket 20 freeze
```

**Candidate membership:** a row is in `candidates[]` **iff** form family ∈
Ticket 20 set **and** `filing_date` ∈ that family’s agent window. Out-of-window
rows never enter the list.

**Contract / SiS:** machine-readable coverage on the Decision Contract **plus**
required human Agent View labels. Forbidden: implying “complete history since
2013” for all relationship forms. Explore wider archives only with non-agent
labels. Exact GO claim phrases → ticket 13 / completion gate.

**Rebuild before GO:** **full freeze rebuild required** (new fingerprint +
per-type membership + `coverage_by_document_type`). Post-filter of the live
2013-era freeze without a new inventory identity is **not** agent GO.

Reconciliation and the Bulk-Load Completion Ledger remain accession-level and
fail-closed; the **denominator** for each form family is “candidates inside
that family’s window,” not “all SEC filings since 2013.”

## Implementation checklist (code follow-up)

Not all of this is implemented until the inventory builder is updated:

1. `build_relationship_release_manifest` / `build_frozen_candidate_manifest`
   accept **per-form lookbacks** and filter candidates by form + filing_date
   (membership rule above).
2. Emit top-level `coverage_start` = min-of-types (index floor) **and**
   `coverage_by_document_type` into freeze + evidence; fingerprint must cover both.
3. Stop treating a single global `coverage_start` as agent coverage for every form.
4. **Rebuild production freeze** under the new windows before claiming GO.
5. Keep absolute floor `2013-05-20` as the 13F XML hard floor inside the 13F
   type start only (`max(W−3y, 2013-05-20)`).

## Ownership

| Role | Responsibility |
| --- | --- |
| Release Owner | Approves / changes lookback table |
| Release Data Operator | Builds freeze with declared windows; binds digests |
| Warehouse Ingestion Builder | Implements per-type filter in inventory |
| Graph / dashboard | Surfaces per-type coverage labels |

## Related docs

- [Required Relationship Bulk-Load Completion Gate](./required-relationship-bulk-load-completion-gate.md)
- [Relationship Eligibility at the Release Watermark](./relationship-eligibility-at-release-watermark.md)
- [Ticket 20 strict bulk-load resume](./ticket20-strict-bulk-load-resume.md)
