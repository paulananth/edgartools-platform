# Agent vs investment-research source relevance windows

**Status:** Release Owner decisions confirmed 2026-07-18 (grill in progress;
remaining items defaulted where noted).  
**Audience:** trading agents (Agent Decision Surface) and humans doing
investment research / analysis.  
**Complements:**
[relationship-source-coverage-by-document-type.md](./relationship-source-coverage-by-document-type.md),
[ADR 0001](../adr/0001-agent-decision-surface-first.md), `CONTEXT.md` Agent
decision support.

## Two different “research” concepts (do not confuse)

| Concept | What it is | Where data comes from | Ticket 20 bulk-load? |
| --- | --- | --- | --- |
| **Investment analysis (CAGR, growth, earnings potential)** | Quant features for decisions | **Companyfacts → silver/gold Decision Features** (FY history as **inputs** to a published as-of row). Agent reads features, does not recompute from raw filings (ADR 0001 / CONTEXT). | **No** — not Form 13F/8-K relationship inventory |
| **Relationship / event sources** | Who employs whom, who holds what, insider/adviser edges | Proxy, Item 5.02 8-K, 13F, ownership, ADV, etc. via relationship bulk-load + MDM/graph | **Yes** — this doc’s windows |
| **Human Explore Mode** | Broader browsing, optional deeper history | Same warehouse tables, **labeled not agent-grade** | Optional later; not agent GO |

**Implication:** Loading less 8-K or less 13F history does **not** break 3y/5y
CAGR. CAGR needs multi-year **financial** facts, not multi-year Item 5.02
filings.

## Product split

| Surface | Who | Truth | History needed |
| --- | --- | --- | --- |
| **Agent Decision Surface** | Trading agents; Human Audit View of same contract | Watermark-aligned Snowflake Decision Contract only | Current-at-watermark edges + **declared** feature lookbacks |
| **Investment research / Explore** | Humans | Gold/graph under Explore labels | May be wider; must not silently expand agent contract |

## Confirmed windows (watermark `W`)

### Relationship sources for agent-useful first GO

| Source | Forms | Relevant from (filing date) | Agent purpose |
| --- | --- | --- | --- |
| **13F** | `13F-HR`, `13F-HR/A` | **`[max(W − 3 years, 2013-05-20), W]`** | `INSTITUTIONAL_HOLDS` current + ~12 quarters context. Wayfinder ticket **Lock 13F agent lookback window** locked 2026-07-18; full XML-era archive not first agent GO. |
| **Proxy** | `DEF 14A`, `DEF 14A/A`, `DEFA14A`, `PRE 14A` | **`[W − 5 years, W]`** only; baseline = latest in band | Wayfinder **Lock proxy agent lookback window** (2026-07-18): **no** load of proxies older than W−5y even as baseline. |
| **Item 5.02 8-K** | `8-K`, `8-K/A` (5.02 or ambiguous items) | **`[W − 2 years, W]`** | Recent appointment/departure events. Wayfinder ticket **Lock Item 5.02 8-K agent lookback window** locked 2026-07-18 (2y, not 1y). Older 5.02 Explore-only. |
| **Unrelated 8-K** | items prove no 5.02 | **Out of scope** | Do not bulk-download |

### Financial / quant features (not Ticket 20 document freeze)

| Feature class | Relevant history | Source path |
| --- | --- | --- |
| CAGR, growth, earnings-potential style factors | **3y / 5y FY inputs** under declared feature rules; published as **one as-of feature row** at `W` | Companyfacts / gold Subject Feature Screen |
| Latest Complete Holdings Period lag | Exposed in coverage metadata | 13F derivation, not extra 8-K years |

### Other relationship types

| Source | Agent window | Notes |
| --- | --- | --- |
| Form 3/4/5 insider | **`[W − 2 years, W]`** activity + **current derived holds** always | Wayfinder **Lock Form 3/4/5 agent lookback window** locked 2026-07-18. **Not** Ticket 20 freeze path (silver-once ownership). Deeper Form 4 tape Explore-only. |
| ADV / MANAGES_FUND | Current ADV + **`W − 2 years`** material changes if published | Default until grilled |
| Auditor | Latest as-of `W` | Default until grilled |
| Parent / EX-21 | Latest 10-K exhibit set as-of `W` | Default until grilled |

## What Ticket 20 must load for agent-aligned GO

Freeze and bulk-load **only** relationship candidates inside the confirmed
table above. Do **not**:

- use global `coverage_start = 2013-05-20` for 8-K or proxy;
- require full 13F since 2013 for first agent GO (3y is enough; 2013 is floor only);
- couple financial CAGR completeness to 13F/8-K document count.

Optional **deeper relationship archives** (13F to 2013, older 8-Ks) are a
**later / separate** pipeline if humans want Explore depth — not required for
agent-grade PASS.

## Mapping to load size (approx., prior freeze math)

Relative to a single 2013→`W` freeze (~529k candidates):

| Cut | Rough effect |
| --- | --- |
| 8-K → 2y only | Large drop in 8-K artifact work vs full history |
| 13F → 3y only | Dominant volume cut vs full XML-era 13F |
| Proxy → baseline + 5y | Already modest vs 13F |

Exact counts require a **new freeze** under per-form filters.

## Implementation checklist

1. Inventory builder: per-form lookbacks (13F 3y/floor, proxy 5y in-band only, 8-K 2y);
   candidates only inside each family’s window (wayfinder ticket 12).
2. Freeze metadata: top-level `coverage_start` = min-of-types **index floor**;
   `coverage_by_document_type` = product truth on freeze + evidence + Decision Contract;
   SiS Agent View required human labels (no universal “complete since 2013”).
3. **Full freeze rebuild** before Ticket 20 agent GO under new windows (no post-filter-only GO).
4. Financial feature pipeline remains separate (companyfacts/gold).
5. Deploy resume (P0–P2) so partial loads compound.

## Ticket 20 PASS / GO claim language (locked 2026-07-18)

PASS = **agent-window bulk-load complete** only (frozen candidates terminal).
Bind every PASS to **fingerprint + watermark W + `coverage_by_document_type`**.

```text
Required relationship sources for EMPLOYED_BY and INSTITUTIONAL_HOLDS are
bulk-load complete for agent windows at watermark W (fingerprint F):
  13F [max(W−3y, 2013-05-20), W];
  proxy [W−5y, W] (latest-in-band baseline only);
  Item 5.02 / ambiguous 8-K [W−2y, W].
```

**Forbidden:** “complete since 2013” for all forms; full-history / all-8-K /
all-proxy-since-IPO claims; 13F full-XML-era when freeze is 3y; Form 3/4/5 or
CAGR as Ticket 20 PASS; top-level `coverage_start` as all-forms agent coverage;
Explore archive = agent GO.

## Grill log

| # | Question | Decision |
| --- | --- | --- |
| 1 | 13F depth for first agent GO | **`W − 3 years`** (floor 2013-05-20) |
| 2 | EMPLOYED_BY sources | **Proxy `[W−5y, W]` in-band only + 8-K 5.02 last 2 years** (locked) |
| 3 | CAGR vs relationship load | **CAGR/growth from companyfacts/gold features, not from deep 13F/8-K bulk-load** (platform doctrine; treat as locked) |
| 4 | Insider Form 4 window | **Locked** **`W − 2 years`** activity + current derived holds (2026-07-18); not Ticket 20 freeze |
| 5 | Deep 13F-to-2013 archive | **Not in first agent GO**; optional later Explore backfill |
| 6 | Freeze encoding + GO phrases | Tickets 12–13: `coverage_by_document_type` truth; rebuild freeze; approved PASS phrases + ban list |

## Related

- [relationship-source-coverage-by-document-type.md](./relationship-source-coverage-by-document-type.md)
- [required-relationship-bulk-load-completion-gate.md](./required-relationship-bulk-load-completion-gate.md)
- [ticket20-strict-bulk-load-resume.md](./ticket20-strict-bulk-load-resume.md)
