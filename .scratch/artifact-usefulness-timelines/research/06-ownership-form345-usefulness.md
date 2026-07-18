# Research: Ownership Form 3/4/5 usefulness timeline

**Ticket:** [06-ownership-form345-usefulness-timeline](../issues/06-ownership-form345-usefulness-timeline.md)  
**Sources:** `CONTEXT.md` (Trading-Relevant Neighborhood; Current Neighborhood), [ADR 0001](../../../docs/adr/0001-agent-decision-surface-first.md), [decision-watermark.md](../../../docs/decision-watermark.md), [agent-and-research-source-relevance-windows.md](../../../docs/release-readiness/agent-and-research-source-relevance-windows.md), [subject-bundle-read.md](../../../docs/subject-bundle-read.md), [product-questions-and-dashboards.md](../../../docs/product-questions-and-dashboards.md) (Insider Watch), silver-once ownership (agent-decision-data-plane ticket 03).

## Question restated

How far back do Forms 3/4/5 remain useful for agent insider / HOLDS signals (current positions + recent activity) vs deep ownership archaeology?

## Two different agent signals

| Signal | What it is | Source tables / edges | History needed |
| --- | --- | --- | --- |
| **Current derived holds** | Positions still open / last reported beneficial ownership for reporting owners on the subject | Gold `ownership_holdings` / graph `HOLDS` / `IS_INSIDER` with gold ownership accession | **Current-at-watermark snapshot**, not a multi-year filing archive of every Form 4 |
| **Recent activity** | Open-market buys/sells, grants, exercises — the “tape” | Gold `ownership_activity` / Form 3–5 transaction rows | Bounded lookback for agent Insider Watch–style context |

Product questions (Explore + agent audit) split the same way: “who are reporting owners / current holdings?” vs “what buys/sells in the last N days/quarters?”

## Usefulness decay

| Age of Form 3/4/5 (filing/period relative to `W`) | Current HOLDS | Activity signal | Agent vs Explore |
| --- | --- | --- | --- |
| **Latest state for each owner–security** | High — drives current holds / IS_INSIDER | N/A for “current” | Agent required |
| **Activity in last ~2 years** | Indirect (updates holdings) | High — recent insider tape, concentration of sells, event context | **Agent default window** |
| **Activity 2–5+ years old** | Low once superseded by later filings | Medium–low for trading agents; useful for multi-year pattern research | Explore / optional Neighborhood History |
| **Deep archaeology (decade+ Form 4 tape)** | None for current-at-watermark | Low for agents; high only for human forensic research | Explore-only |

**Decay principle:** For agents, **current holds matter more than ancient transactions**. A Form 4 from 2015 that was fully unwound and superseded does not belong in the default Current Neighborhood; a Form 4 last month that changed the position does.

## Recommended agent activity window

From `agent-and-research-source-relevance-windows.md` (grill default #4, until product overrides):

```text
Forms: 3, 4, 5 (and amendments as applicable)
Activity lookback: W − 2 years  (filing/transaction dates in window)
Plus: current derived holds (snapshot at W, independent of full multi-year tape)
```

| Option | When to use |
| --- | --- |
| **`W − 2 years` activity + current holds** | **Recommended agent v1 default.** Covers ~8 quarters of insider tape; enough for “recent selling / buying around events” without decade-scale bulk. |
| **`W − 1 year` activity + current holds** | Acceptable if product wants a tighter GO surface; slightly less event context. Not required by doctrine; only if Release Owner overrides. |
| **Full history since first Form 3** | Explore / deep research; **not** first agent GO. |

Current holds derivation may **use** older filings as chain-of-title inputs in the warehouse/MDM path, but the **agent-facing activity section** and bulk-load **GO claim** for “insider activity complete” should be labeled against the **declared activity window**, not “all Form 4s ever.”

## Silver-once ownership path (not Ticket 20 freeze)

Ownership Forms 3/4/5 are **not** the same pipeline as Ticket 20 relationship bulk-load for proxy / Item 5.02 8-K / 13F:

| Concern | Ownership path | Ticket 20 relationship freeze |
| --- | --- | --- |
| Ingest | Branch A / artifact capture; `parse-ownership-bronze` reparse from bronze | Strict relationship candidate ledger + bulk artifact load for employment/13F |
| Idempotency | **Silver-once** skip by accession + `parser_version` (data-plane ticket 03) | Accession-level bulk-load completion ledger for required relationship candidates |
| Agent edges | `IS_INSIDER`, `HOLDS`, `COMPANY_HOLDS` from ownership silver → MDM → graph | `EMPLOYED_BY`, `INSTITUTIONAL_HOLDS` primarily from proxy/8-K/13F |
| Freeze coupling | May appear in broader universe loads; **agent usefulness window** for activity is still **~2y + current holds** — do not force a 2013 global ownership archive for agent GO | Per-form windows already locked for 13F/proxy/8-K |

**Do not** treat ownership depth as a reason to expand Ticket 20’s 13F/8-K/proxy freeze. **Do not** treat Ticket 20 completion as proof that Form 3/4/5 activity history is complete for the agent window.

## Explore-tier

- Multi-year / full-career insider tapes beyond 2y.
- Forensic reconstruction of every grant/exercise since IPO.
- Cross-issuer “all historical Form 4s for person P” without current-at-watermark filters (unless explicitly labeled Explore).

## Exit criteria map

| Criterion | Answer |
| --- | --- |
| Current derived holds vs activity | **Separate:** holds = current snapshot; activity = bounded lookback. |
| Recommended agent activity window | **`W − 2 years`** (+ current holds). 1y is optional tighter override. |
| Silver-once / Ticket 20 | Ownership is silver-once / Branch A path; not the Ticket 20 relationship freeze driver. |

## Pointers

| Doc / code | Relevance |
| --- | --- |
| `docs/release-readiness/agent-and-research-source-relevance-windows.md` | Default Form 3/4/5 = `W − 2y` + current holds |
| `docs/subject-bundle-read.md` | `insiders` section: graph + gold ownership accession |
| `docs/product-questions-and-dashboards.md` §C | Insider product questions |
| `docs/aws-mdm-source-to-mdm.md` | `parse-ownership-bronze` |
| `.scratch/agent-decision-data-plane/issues/03-silver-once-ownership.md` | Silver-once skip |
| `edgar_warehouse/parsers/ownership.py` | Form 3/4/5 parse via edgartools |
| Lock ticket | [11-lock-insider-form345-agent-window](../issues/11-lock-insider-form345-agent-window.md) |
