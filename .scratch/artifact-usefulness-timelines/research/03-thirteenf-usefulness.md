# Research: Form 13F usefulness timeline

**Ticket:** [03-thirteenf-usefulness-timeline.md](../issues/03-thirteenf-usefulness-timeline.md)  
**Date:** 2026-07-18  
**Principle:** Old data has less value for agent **current-at-watermark** decisions.

## Sources consulted

| Source | Role |
| --- | --- |
| [agent-and-research-source-relevance-windows.md](../../../docs/release-readiness/agent-and-research-source-relevance-windows.md) | Confirmed agent windows (grill #1: `W−3y`, floor 2013-05-20) |
| [relationship-source-coverage-by-document-type.md](../../../docs/release-readiness/relationship-source-coverage-by-document-type.md) | Per-type freeze policy; 13F not universal 2013 load |
| [required-relationship-bulk-load-completion-gate.md](../../../docs/release-readiness/required-relationship-bulk-load-completion-gate.md) | Gate semantics for `INSTITUTIONAL_HOLDS`; amendment load rules |
| [ADR 0001](../../../docs/adr/0001-agent-decision-surface-first.md) | Holdings “current” = Latest Complete Holdings Period + lag in coverage |
| [product-questions-and-dashboards.md](../../../docs/product-questions-and-dashboards.md) | Same 13F currency product decision |
| [subject-bundle-read.md](../../../docs/subject-bundle-read.md) | Bundle sections `holders_of_subject` / `subject_as_manager_portfolio` |
| `edgar_warehouse/application/effective_thirteenf.py` | Restatement supersedes; added-holdings supplements; per (manager, period) |
| SEC Form 13F FAQ / form instructions (linked from gate doc) | XML information-table era; amendment types |

## What 13F is used for

### (a) Agent Decision Surface — `INSTITUTIONAL_HOLDS`

- **Current-at-watermark edge set:** manager → security positions from the
  **effective public filing set** for each complete report period that is
  admissible under the Latest Complete Holdings Period rule.
- **Short change context:** successive quarterly effective sets so the agent
  can see who entered/exited or scaled a position over a modest horizon
  (~12 quarters ≈ 3 years), not a multi-decade ownership archaeology.
- **Currency model:** deliberately **lagged**. ADR 0001 and product table lock
  “holdings current” as **Latest Complete Holdings Period** with lag exposed in
  coverage — not same-day positions. Extra calendar years of raw 13F-HR do not
  make the edge “fresher”; they only deepen historical context.
- **Amendment semantics** (`effective_thirteenf.py`):
  - Group by `(manager_cik, period_of_report)`.
  - Restatement (or later non-addition base) **supersedes** prior base + prior
    additions for that period.
  - `added_holdings` amendments **supplement** the current base without
    replacing unchanged rows.
  - Confidential omissions are not asserted until public via a later amendment
    (gate language).
  - Implication for age: a 2014 restated period’s superseded originals are
    **history for audit/Explore**, not agent current-neighborhood inputs once a
    later effective set exists for that period — and for *current* decisions
    only the latest complete periods matter.

### (b) Human investment analysis / Explore

- Multi-year manager style, long run-up of AUM concentration, multi-cycle
  ownership of an issuer, and forensic “who held during X” questions can use
  deeper 13F archives.
- Those questions are **Explore / research**, not the Agent Decision Surface
  contract. They must not expand Ticket 20’s first GO freeze denominator by
  silently requiring full XML-era load for agent PASS.

## Value-vs-age narrative

| Horizon | What it buys | Agent value | Explore value |
| --- | --- | --- | --- |
| **Latest complete period only** | Current `INSTITUTIONAL_HOLDS` snapshot | **Necessary** for neighborhood | Baseline |
| **~4 quarters (1y)** | One year of QoQ flow | Useful but thin for “change context” | Light flow |
| **~12 quarters (3y)** | Short structural change, regime shifts, multi-year accumulation/exit | **Sweet spot** for agent change context | Strong research default |
| **5y+ within XML era** | Longer style / cycle analysis | **Diminishing** for current-at-W decisions | Optional Explore |
| **Full XML era → `2013-05-20`** | Format-complete institutional history | **Not required** for first agent GO | Optional deep archive |
| **Pre-`2013-05-20`** | Pre-XML information tables | **Out of claim** — hard floor; cannot assert pre-XML 13F completeness | Out of platform claim |

**Decay principle (step, not continuous):** usefulness does not fall as a smooth
curve that must be parameterized; the product uses **step lookbacks**. Beyond
~3 years, incremental filings mostly serve human narrative, not watermark-aligned
trading-neighborhood edges. Loading them for agent GO inflates bulk-load volume
(dominant freeze cost vs proxy/8-K) without improving Latest Complete Holdings
Period correctness.

## SEC lag / Latest Complete Holdings Period

- 13F is filed **after** period end (classic institutional lag; platform treats
  lag as first-class coverage metadata, not a defect to fix by loading more
  years).
- Agent “current” = effective holdings for the **latest complete reportable
  period ≤ W**, not positions as of wall-clock `W`.
- Completeness of that period requires **all** `13F-HR` / `13F-HR/A` for managers
  in that period’s SEC quarterly indexes (and amendment effectiveness), not
  decades of prior periods.
- Prior periods inside the lookback support **declared change context** only.

## Format floor vs agent lookback

| Concept | Date / rule | Meaning |
| --- | --- | --- |
| **XML hard floor** | `2013-05-20` | Earliest date we will claim machine-parseable information-table 13F; never claim pre-XML completeness |
| **Agent lookback start** | `max(W − 3 years, 2013-05-20)` | Product usefulness window for first agent GO freeze |
| **Explore optional** | `2013-05-20` → `W` (or longer only if still ≥ floor) | Separate later pipeline; not first agent GO |

`DEFAULT_COVERAGE_START = 2013-05-20` in
`edgar_warehouse/application/relationship_bulk_load.py` is the **format floor
default**, not proof that agents need full history since 2013. Coverage docs
explicitly supersede a single global 2013 start for all form families.

## Recommended windows

### Agent (first GO / Ticket 20 relationship freeze)

```text
thirteenf: { start: max(W - 3y, 2013-05-20), end: W }
```

**Rationale validation:**

1. **Current-at-W** only needs the Latest Complete Holdings Period + effective
   amendment set — a short tail of history, not the full XML archive.
2. **~12 quarters** is the confirmed product grill depth for “short change
   context” without treating multi-decade 13F as agent inputs
   (`agent-and-research-source-relevance-windows.md` grill #1).
3. **Floor** preserves correctness when `W − 3y` would predate the XML era
   (e.g. early product watermarks or unit tests near 2013–2016).
4. **Volume:** 3y cut is the dominant bulk-load savings vs full XML-era 13F
   while keeping fail-closed completeness **inside** the window.
5. **Financial multi-year features (CAGR etc.)** stay on companyfacts/gold —
   they do **not** justify deeper 13F document history for agents.

### Explore / human analysis (optional, not first agent GO)

```text
thirteenf_explore: { start: 2013-05-20, end: W }   # optional separate backfill
```

- May deepen manager/issuer archaeology; must be labeled **not agent-grade** if
  wider than the agent window.
- Must still respect the XML floor.

### Rejected alternatives for agent GO

| Option | Why reject |
| --- | --- |
| Latest period only | No declared QoQ/change context; product grill chose ~12 quarters |
| Fixed 5y without product need | Extra volume; diminishing agent value |
| Full `2013-05-20` → W as agent GO | Over-loads freeze; confuses format floor with usefulness |
| Pre-2013 paper/ASCII tables | Outside platform claim / parser contract |

## Gate / inventory implications

- Institutional Holdings inventory = every `13F-HR` / `13F-HR/A` in every
  complete SEC quarterly index from **13F window start** through `W`
  (manager universe, not only tracked issuers).
- Per-period effective set after load: restatement supersedes; added-holdings
  supplements (`effective_thirteenf.py`).
- Freeze metadata should record `coverage_by_document_type.thirteenf`, not a
  single global `coverage_start` shared with 8-K/proxy.
- Decision Contract coverage should expose Latest Complete Holdings Period +
  lag; agents abstain or treat as partial when period incomplete.

## Exit criteria checklist

| Criterion | Result |
| --- | --- |
| Value-vs-age narrative | Table above; step decay after ~3y for agent current-at-W |
| Recommended agent window | **`max(W − 3 years, 2013-05-20)`** |
| Optional Explore window | Full XML-era `2013-05-20` → `W` (separate, not first GO) |
| SEC lag / LCHP | Lagged source OK; lag in coverage; not fixed by more years |

## Recommendation (one line)

**Agent:** `max(W−3y, 2013-05-20)` through `W`. **Explore:** optional full XML-era archive. Do not require 2013→W for first agent GO.
