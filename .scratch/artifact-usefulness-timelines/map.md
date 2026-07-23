# Artifact usefulness timelines (agent + investment analysis)

Type: wayfinder:map
Status: resolved
Labels: wayfinder:map

## Destination

A **locked, document-by-document usefulness timeline table** (lookback start
relative to Release Data Watermark `W`, format floors, agent vs Explore) that
agents and investment analysis can rely on — so bulk-load freezes, Decision
Contract coverage labels, and Ticket 20 denominators match **decaying value of
old data**, not a single global 2013 start for every form.

**Destination met 2026-07-18:** agent windows, freeze encoding, and GO claim
language are locked (tickets 01–13). Implementers may rebuild the relationship
freeze and feature pipelines without reopening “how far back?” for each artifact
family. Code/execution remains out of scope for this map.

## Notes

- Domain: EdgarTools platform — Agent Decision Surface (Snowflake contract) and
  human investment analysis (Explore Mode). Agents never read bronze/silver.
- **Planning only** unless a ticket is Type: task that unblocks a decision.
- Consult: `CONTEXT.md` (Agent decision support), `docs/adr/0001-agent-decision-surface-first.md`,
  `docs/release-readiness/agent-and-research-source-relevance-windows.md`,
  `docs/release-readiness/relationship-source-coverage-by-document-type.md`,
  `docs/release-readiness/required-relationship-bulk-load-completion-gate.md`.
- Standing preference: **old data has less value** for agent current-at-watermark
  decisions; long history may still matter for Explore or multi-year financial
  *feature inputs* (CAGR), which are **not** the same as loading every 8-K/13F.
- CAGR / growth / earnings-potential features come from **companyfacts → gold
  features** (multi-year FY **inputs** to an as-of row), not from Ticket 20
  relationship document bulk-load.
- 13F **format floor** `2013-05-20` is XML-era correctness, not “must load full
  history for agents.”

## Decisions so far

- [Catalog agent-grade vs analysis artifacts](issues/01-catalog-agent-and-analysis-artifacts.md) — Split Agent Decision Surface vs Explore; Ticket 20 freeze owns 13F/proxy/5.02 only; companyfacts/CAGR and Form 3/4/5/ADV/auditor stay other paths. Research: [research/01-artifact-catalog.md](research/01-artifact-catalog.md).
- [Form 13F usefulness timeline](issues/03-thirteenf-usefulness-timeline.md) — Agent: `max(W−3y, 2013-05-20)`; full XML-era archive is Explore backfill, not first agent GO. Research: [research/03-thirteenf-usefulness.md](research/03-thirteenf-usefulness.md).
- [Item 5.02 8-K usefulness timeline](issues/04-item-502-8k-usefulness-timeline.md) — Agent: **W−1y** for 5.02/ambiguous; unrelated 8-K out of bulk download. Research: [research/04-item-502-usefulness.md](research/04-item-502-usefulness.md).
- [Proxy (DEF 14A family) usefulness timeline](issues/05-proxy-usefulness-timeline.md) — Latest proxy ≤W always + **W−5y** history; older non-baseline proxies Explore-only. Research: [research/05-proxy-usefulness.md](research/05-proxy-usefulness.md).
- [Ownership Form 3/4/5 usefulness timeline](issues/06-ownership-form345-usefulness-timeline.md) — Current holds + **W−2y** activity; not Ticket 20 freeze path. Research: [research/06-ownership-form345-usefulness.md](research/06-ownership-form345-usefulness.md).
- [Financial feature history is not relationship freeze](issues/07-financial-feature-history-not-relationship-freeze.md) — CAGR/growth from companyfacts→gold (3y/5y FY inputs); orthogonal to 13F/8-K depth. Research: [research/07-financial-features-vs-relationship-freeze.md](research/07-financial-features-vs-relationship-freeze.md).
- [Confirm destination and old-data decay principle](issues/02-confirm-destination-and-decay-principle.md) — **Agent-first GO**; decay = **step lookbacks per form**; investment research = quant features (companyfacts/gold) + optional Explore archive (not first agent PASS).
- [Lock 13F agent lookback window](issues/08-lock-thirteenf-agent-window.md) — Agent 13F: originally `[max(W−3y, 2013-05-20), W]`, narrowed to 1y (PR #217) then to **`[max(W−1 quarter, 2013-05-20), W]`** (2026-07-23, no standalone value in history); full 2013→W archive **not** in first agent GO freeze (Explore backfill only).
- [Lock Item 5.02 8-K agent lookback window](issues/09-lock-item-502-8k-agent-window.md) — Agent 8-K 5.02/ambiguous: **`[W−2y, W]`**; older 5.02 Explore-only; non-5.02 items never bulk-downloaded.
- [Lock proxy agent lookback window](issues/10-lock-proxy-agent-window.md) — Agent proxy: **`[W−5y, W]`** only; baseline = latest in band; **no** pre–W−5y baseline exception.
- [Lock Form 3/4/5 agent lookback window](issues/11-lock-insider-form345-agent-window.md) — Activity **`[W−2y, W]`** + current derived holds always; **not** Ticket 20 freeze path; deeper Form 4 tape Explore-only.
- [Freeze encoding and coverage labels](issues/12-freeze-encoding-and-coverage-labels.md) — `coverage_by_document_type` = product truth; top-level `coverage_start` = min-of-types index floor only; candidates only in-window; Contract+SiS machine+human labels; **full freeze rebuild required** before GO.
- [GO claim language for partial history](issues/13-go-claim-language-for-partial-history.md) — PASS = agent-window bulk-load complete only; bind F+W+`coverage_by_document_type`; approved phrases + forbidden overclaims (no “complete since 2013” for all forms).

### Canonical agent windows (implementer table)

| Family | Agent window | Ticket 20 freeze? |
| --- | --- | --- |
| **13F** | `[max(W−3y, 2013-05-20), W]` | Yes |
| **Proxy** | `[W−5y, W]` (latest-in-band baseline; no pre-band) | Yes |
| **Item 5.02 8-K** | `[W−2y, W]` (ambiguous in-window; non-5.02 never) | Yes |
| **Form 3/4/5** | `[W−2y, W]` activity + current holds | No (ownership path) |
| **CAGR / features** | 3y/5y FY inputs → as-of gold row | No (companyfacts path) |

## Not yet specified

- Exact quantitative decay curves (e.g. “value halves every N quarters”) beyond
  step lookbacks — not required; step lookbacks locked.
- Manager-bundle (ADV) vs issuer-bundle windows in one freeze vs two freezes
  (out of Ticket 20 first agent GO).

## Out of scope

- Implementing the freeze builder / production reload (execution after map).
- Trading execution, order routing, portfolio management.
- Non-AWS paths; public customer launch.
- Reopening dual-mode capture / silver SoE ADRs.
- Loading every SEC form type “just in case.”
