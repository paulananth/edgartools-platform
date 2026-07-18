# Research: Item 5.02 8-K usefulness timeline

**Ticket:** [04-item-502-8k-usefulness-timeline.md](../issues/04-item-502-8k-usefulness-timeline.md)  
**Date:** 2026-07-18  
**Principle:** Old data has less value for agent **current-at-watermark** decisions.

## Sources consulted

| Source | Role |
| --- | --- |
| [agent-and-research-source-relevance-windows.md](../../../docs/release-readiness/agent-and-research-source-relevance-windows.md) | Confirmed: Item 5.02 8-K = `W−1y`; grill #2 EMPLOYED_BY stack |
| [relationship-source-coverage-by-document-type.md](../../../docs/release-readiness/relationship-source-coverage-by-document-type.md) | 1y 8-K window; unrelated 8-K out of scope; proxy baseline rules |
| [required-relationship-bulk-load-completion-gate.md](../../../docs/release-readiness/required-relationship-bulk-load-completion-gate.md) | `EMPLOYED_BY` semantics; candidate selection for 5.02 / ambiguous |
| [ADR 0001](../../../docs/adr/0001-agent-decision-surface-first.md) | Current Neighborhood default; history optional |
| [subject-bundle-read.md](../../../docs/subject-bundle-read.md) | `employment` section: `proxy_def14a` or `item_5_02` |
| `edgar_warehouse/parsers/item_502.py` | Appointment/departure/role/comp events; `apply_employment_events` temporal versions |
| SEC Form 8-K Item 5.02 definition (linked from gate) | Director/officer departure, election/appointment, compensatory arrangements |

## What Item 5.02 is used for

`EMPLOYED_BY` = **Reported Executive Employment** (named executive / covered
officer), **not** a full employee roster.

Evidence stack (agent):

1. **Proxy baseline** — latest definitive proxy on or before `W` always in
   scope (may predate the 5y proxy history band); plus proxies ≥ `W−5y` for
   multi-year officer set.
2. **Item 5.02 (and ambiguous-item) 8-Ks** — filing date in **`[W−1y, W]`** —
   appointments, departures, role changes, covered compensatory events that
   **update** employment versions after the baseline.

Parser shape (`item_502.py`):

- Scopes to the Item 5.02 section only (multi-item 8-Ks otherwise leak
  verbs from other items).
- Emits `EmploymentEvent` rows (appointment / departure / role_change /
  compensation_change).
- `apply_employment_events` walks events by effective date: appointments open
  new open-ended versions; departures close the matching open version
  (`valid_to`). Old closed versions remain history; **agent current-at-W**
  cares about open versions and recent open/close transitions.

## Why usefulness decays fast vs proxy

| Layer | Cadence | Role at watermark W | Value of multi-year depth |
| --- | --- | --- | --- |
| **DEF 14A / proxy** | ~Annual | **Baseline roster** of reported officers/NEOs and pay | Multi-year proxies support officer-set history (product: 5y + always-latest baseline) |
| **Item 5.02 8-K** | Event-driven (intra-year) | **Delta** since last proxy / since last event — who joined, left, or changed role | Only **recent** events change the current neighborhood; a 2019 appointment is already in later proxies if still employed, or closed if they left |

**Agent narrative:**

- At decision time the agent needs “who is employed / was just hired or fired
  as of W,” not a complete archaeology of every board appointment since 2013.
- Once a later **proxy** is filed, it re-baselines the officer set; older 5.02
  appointments that still hold are **re-stated** in proxy compensation
  disclosure. Older 5.02 departures already closed edges; replaying them years
  later does not change current-at-W open versions if subsequent proxies and
  events were applied.
- Therefore multi-year 8-K history is mostly **event archaeology** (Explore /
  forensic “when did X leave?”), not required bulk input for agent GO.

**Volume narrative:**

- Unfiltered 8-K history is dominated by **non-employment** items (earnings
  2.02, other 5.x, etc.). Even Item 5.02 / ambiguous candidates explode if the
  window is multi-year.
- Cutting artifact-required 8-Ks to **1 year** is called out as a large drop in
  bulk artifact work relative to a 2013→W freeze
  (`agent-and-research-source-relevance-windows.md` load-size table).

## Ambiguous-item 8-Ks

Gate rule:

- **Has Item 5.02 in metadata + filing_date ≥ W−1y** → candidate; parse primary
  document for employment events.
- **Missing / ambiguous items + filing_date ≥ W−1y** → still a candidate; must
  fetch and classify (fail-closed inside the window).
- **Items prove no 5.02** → **out of scope** for bulk download;
  metadata-backed `not_applicable`; do **not** treat earnings 8-Ks as
  employment candidates.

Ambiguous filings do **not** justify a longer window: classification cost is
paid only for recent ambiguity where events could still move current
employment versions.

## Value-vs-age narrative

| Horizon | Agent current-at-W value | Explore / archaeology |
| --- | --- | --- |
| **0–~12 months (W−1y)** | High — post-proxy appointments/departures not yet in annual DEF 14A; closes/opens versions agents need | High |
| **1–5 years** | Low for **current** edges if proxy baselines + recent 5.02 applied; may help reconstruct intermediate tenure for humans | Useful timeline |
| **5y+ / to 2013** | Negligible for agent neighborhood; risk of huge low-value volume | Optional deep archive only |

**Decay principle:** step lookback, not continuous half-life. Beyond one year,
5.02 filings are subordinate to the proxy baseline for “who is reported
employed now.”

## Recommended windows

### Agent (first GO / Ticket 20)

```text
item_502_8k: { start: W - 1 year, end: W }
# forms: 8-K, 8-K/A with Item 5.02 OR missing/ambiguous items only
# unrelated 8-K (items prove no 5.02): out of bulk-download scope
```

**Rationale validation for “one year is sound”:**

1. **Proxy carries the baseline.** Latest DEF 14A ≤ W is always loaded (even if
   older than 5y for baseline-only). Agent employment is not “8-K-only.”
2. **5.02 is a freshening delta.** Intra-year officer changes between proxies
   are what agents miss without recent 8-Ks; a full year covers a typical
   annual-meeting / proxy cycle gap with margin for late amendments (`8-K/A`).
3. **Temporal application** (`apply_employment_events`) only needs events that
   can still open/close versions relative to that baseline and later events;
   ancient closed tenures do not alter current neighborhood edges.
4. **Product grill confirmed** `W−1y` for Item 5.02
   (`agent-and-research-source-relevance-windows.md` grill #2:
   proxy baseline + 5y proxies + 8-K 5.02 last 1 year).
5. **Cost/claim alignment:** avoids implying “complete 8-K employment history
   since 2013” on dashboards and freeze denominators.

### Explore optional extension

```text
item_502_8k_explore: { start: W - 5y | custom, end: W }  # optional human archive
# still exclude unrelated 8-Ks; never use as silent agent expansion
```

- Use for forensic “full tenure timeline” or multi-year leadership churn
  research.
- **Not** required for agent-grade PASS; label not agent-grade if wider than
  `W−1y`.
- Still do not bulk-download unrelated 8-Ks.

### Unrelated 8-K exclusion (confirmed)

| Case | Bulk download? | Terminal / reason |
| --- | --- | --- |
| Items include 5.02, date ≥ W−1y | Yes | Parse → events or evidenced no-employment-event |
| Items missing/ambiguous, date ≥ W−1y | Yes | Classify then same |
| Items prove no 5.02 | **No** | `not_applicable` from metadata |
| Any of the above but date &lt; W−1y | **No** for agent GO denominator | Out of window (Explore only if product expands) |

## Coupling notes (do not break)

- **Do not** couple 8-K years to financial CAGR completeness — CAGR is
  companyfacts/gold features, not Item 5.02 count.
- **Do not** apply 13F’s `2013-05-20` floor as an 8-K load mandate.
- **Do not** shorten proxy windows because 8-K is 1y; proxy remains
  baseline + 5y history band.
- Current MDM derivation gap (proxy-only `EMPLOYED_BY`, no Item 5.02 path yet)
  is an **implementation** blocker in the gate doc — it does **not** change the
  usefulness window recommendation.

## Exit criteria checklist

| Criterion | Result |
| --- | --- |
| Why recent 5.02 &gt; multi-year 8-K given proxy baselines | Proxy re-baselines roster; 5.02 is short-horizon delta for open versions |
| Recommended agent window | **`W − 1 year`** for 5.02 / ambiguous `8-K`/`8-K/A` |
| Explore optional extension | Wider 5.02 archive optional, labeled not agent-grade |
| Unrelated 8-Ks out of bulk download | **Confirmed** |

## Recommendation (one line)

**Agent:** Item 5.02 / ambiguous 8-Ks with filing date ≥ **`W−1y`**. **Explore:** optional deeper 5.02 history only. **Unrelated 8-Ks:** never bulk-download for this relationship path.
