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
| **Proxy compensation / employment baseline** | `DEF 14A`, `DEF 14A/A`, `DEFA14A`, `PRE 14A` | **Latest definitive proxy on or before `W` is always in scope**, plus proxies with filing date ≥ **`W − 5 years`** | Confirmed: baseline + 5y history for `EMPLOYED_BY`. |
| **Item 5.02 employment events (8-K)** | `8-K`, `8-K/A` with Item 5.02 **or** missing/ambiguous items | Filing date ≥ **`W − 1 year`** | Confirmed: one year is enough for agent employment events. |
| **Unrelated 8-K** (items prove no 5.02) | `8-K`, `8-K/A` | **Out of scope** for bulk download | Metadata `not_applicable`; do not treat earnings 8-Ks as employment candidates. |

Notes:

1. **Document-by-document** means: a filing’s eligibility is decided from its
   **form family + filing_date (+ items for 8-K)**, not from “any document for
   this CIK since 2013.”
2. **8-K one year** applies to **artifact-required** Item 5.02 / ambiguous
   8-Ks. It does **not** shorten 13F or proxy windows.
3. **Current-at-watermark** for `EMPLOYED_BY` still requires:
   - latest applicable definitive proxy on or before `W` (even if older than
     five years — baseline only), and  
   - relevant Item 5.02 8-Ks with filing date in **`[W−1y, W]`** after that
     baseline (and in window).
4. If a proxy baseline is older than five years, load **that one baseline
   proxy** plus proxies in the five-year history band; do not require every
   proxy since 2013 unless the Release Owner expands the proxy window.
5. **Dashboard / generation** language must state each type’s coverage start so
   users never read “complete history since 2013” for 8-K employment events.

## Why not one global 2013 start for everything

| Concern | Global 2013 | Per-document windows |
| --- | --- | --- |
| 13F XML correctness | Needed | Keep 2013 floor for 13F only |
| Bulk-load cost | Dominated by 13F + years of 8-K noise | 8-K cut to 1y removes large low-value volume |
| Product claim | Over-claims 8-K history | Matches how employment is used (recent events + proxy) |
| Ticket 20 GO | Single huge freeze | Freeze still fail-closed **inside each type’s window** |

## Freeze / inventory requirements

The frozen candidate manifest (or equivalent per-type inventories) must record:

```text
coverage_by_document_type:
  thirteenf: { start: "2013-05-20" | "W-Ny", end: "W" }
  proxy:     { start: "W-5y" | baseline_exception, end: "W" }
  item_502_8k: { start: "W-1y", end: "W" }
watermark: "W"
```

Reconciliation and the Bulk-Load Completion Ledger remain accession-level and
fail-closed, but the **denominator** for each form family is “candidates inside
that family’s window,” not “all SEC filings since 2013.”

## Implementation checklist (code follow-up)

Not all of this is implemented until the inventory builder is updated:

1. `build_relationship_release_manifest` / `build_frozen_candidate_manifest`
   accept **per-form lookbacks** (or filter candidates after freeze by form +
   filing_date).
2. Stop using a single `coverage_start` for 8-K the same as 13F.
3. Emit freeze metadata `coverage_by_document_type` into the evidence artifact.
4. Rebuild production freeze under the new windows before claiming GO.
5. Optional: keep absolute floor 2013 for 13F only in `DEFAULT_COVERAGE_START`.

Until code ships, operators may approximate by building a freeze with a global
start of `W-1y` **only if** they **exclude** 13F completeness claims, or by
post-filtering the existing freeze to drop 8-Ks older than `W-1y` while
keeping 13F/proxy rows — prefer proper per-type freeze generation.

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
