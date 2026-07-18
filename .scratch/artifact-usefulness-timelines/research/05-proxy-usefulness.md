# Research: Proxy (DEF 14A family) usefulness timeline

**Ticket:** [05-proxy-usefulness-timeline](../issues/05-proxy-usefulness-timeline.md)  
**Sources:** `CONTEXT.md` (Agent decision support; Reported Executive Employment), [ADR 0001](../../../docs/adr/0001-agent-decision-surface-first.md), [decision-watermark.md](../../../docs/decision-watermark.md), [agent-and-research-source-relevance-windows.md](../../../docs/release-readiness/agent-and-research-source-relevance-windows.md), [relationship-source-coverage-by-document-type.md](../../../docs/release-readiness/relationship-source-coverage-by-document-type.md), [subject-bundle-read.md](../../../docs/subject-bundle-read.md).

## Question restated

How far back do definitive proxies remain useful for agent employment baselines and multi-year officer sets, versus “latest proxy only”?

## Role of proxies for the agent

Proxies feed **Reported Executive Employment** (`EMPLOYED_BY`) and executive pay context on the Decision Graph Bundle (`employment` section; `source_system` `proxy_def14a`). They are a **relationship / event source**, not a financial-feature source.

Agent purpose at watermark `W`:

| Need | Why proxy depth matters |
| --- | --- |
| **Current-at-watermark officers / named executives** | Latest definitive proxy on or before `W` is the **employment baseline** even if that filing is older than any rolling history band. |
| **Multi-year officer set / continuity** | Proxies in a bounded history band show who was reported as NEO/officer across recent annual seasons (joins/leaves inferred with Item 5.02 8-Ks). |
| **Compensation as context** | Gold proxy pay rows attach to employment; agent does not recompute pay from raw HTML. |

Companions (not substitutes for proxy baseline):

- Item 5.02 8-K: **`W − 1 year`** only (recent appointment/departure events).
- Forms 3/4/5: insider/HOLDS path (separate ticket 06), not the employment baseline.

## Usefulness decay (value vs age)

| Age of proxy (filing date relative to `W`) | Agent usefulness | Explore / research usefulness |
| --- | --- | --- |
| **Latest definitive ≤ `W`** | **Required.** Baseline for current `EMPLOYED_BY` / named executive roster; may predate the 5y band. | Required for any serious company view. |
| **Within `W − 5 years` (plus latest)** | **Agent GO history band.** Multi-year officer set, year-over-year NEO continuity, compensation trajectory used as neighborhood context. | Primary human research band. |
| **Older than 5y but not the single latest baseline** | **Low for agent current-at-watermark.** Does not change “who is employed now”; optional Neighborhood History only. | Explore-tier deep compensation/officer archaeology. |
| **Every proxy since 2013 / full archive** | **Not required** for agent-grade PASS. Over-claims history; inflates Ticket 20 denominators. | Optional deep archive; not first GO. |

**Decay principle:** Old data has less value for **current-at-watermark** decisions. Proxy value is front-loaded: one baseline + a few recent seasons, not a multi-decade DEF 14A archive.

## Recommended agent window (confirmed product)

From release-readiness windows and coverage-by-document-type:

```text
Forms: DEF 14A, DEF 14A/A, DEFA14A, PRE 14A
End:   W (Release Data / Decision Watermark, inclusive)

Load set =
  { latest definitive proxy with filing_date ≤ W }   # baseline; always
  ∪ { proxies with filing_date ≥ W − 5 years }         # history band
```

Notes:

1. **Baseline may predate `W − 5y`.** If an issuer’s last definitive proxy is 6+ years old, still load **that one** filing as baseline; do **not** expand to every intervening year since 2013.
2. **Baseline + 5y is already modest** relative to 13F volume; further cutting to “latest only” drops multi-year officer continuity that product grilled as in-scope for `EMPLOYED_BY`.
3. **Amendments** (`DEF 14A/A`, `DEFA14A`) in window supersede/supplement under normal amendment semantics; PRE 14A is in family when used as candidate metadata (prefer definitive when both exist for the same season).

## What is Explore-only

- Proxies **older than the 5y band** that are **not** the single latest baseline.
- Full multi-decade compensation archaeology, peer-year pay tables from ancient seasons, or “every DEF 14A ever filed for CIK.”
- Treating global `coverage_start = 2013-05-20` as a proxy mandate (that date is the **13F XML floor only**).

Explore Mode may surface wider gold SQL under **explicit non-agent-grade labels**; it must not silently expand the Agent Decision Surface or Ticket 20 GO denominator.

## Interaction with Ticket 20 / freeze

- Freeze inventory must encode **per-type** proxy coverage:  
  `proxy: { start: "W-5y" | baseline_exception, end: "W" }`  
  (see relationship-source-coverage-by-document-type).
- Proxy depth is **not** coupled to companyfacts / CAGR completeness (ticket 07).
- `EMPLOYED_BY` GO still also needs Item 5.02 8-Ks in **`[W−1y, W]`** after the baseline; that is a separate form-family window.

## Exit criteria map

| Criterion | Answer |
| --- | --- |
| Role of **baseline proxy** | Always load latest definitive ≤ `W`, even if older than 5y. |
| Recommended history band for agent GO | **`W − 5 years`** proxies **plus** baseline. |
| Older proxies | Explore-tier only (except the one baseline filing). |

## Pointers

| Doc / code | Relevance |
| --- | --- |
| `docs/release-readiness/agent-and-research-source-relevance-windows.md` | Confirmed: baseline + 5y |
| `docs/release-readiness/relationship-source-coverage-by-document-type.md` | Freeze encoding; baseline exception |
| `CONTEXT.md` — Reported Executive Employment | Proxy + Item 5.02 scope of `EMPLOYED_BY` |
| ADR 0001 | Current Neighborhood; agents read Snowflake contract only |
| `docs/subject-bundle-read.md` | `employment` section contract |
| Lock ticket | [10-lock-proxy-agent-window](../issues/10-lock-proxy-agent-window.md) |
