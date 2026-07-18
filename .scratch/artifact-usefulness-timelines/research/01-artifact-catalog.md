# Artifact family catalog — agent surface vs analysis / Explore

**Ticket:** `.scratch/artifact-usefulness-timelines/issues/01-catalog-agent-and-analysis-artifacts.md`  
**Date:** 2026-07-18  
**Status:** research complete  

## Purpose

Catalog distinct **artifact / form families** that feed (a) the Agent Decision
Surface (Decision Graph Bundle / Subject Feature Screen / Snowflake Decision
Contract) and (b) investment analysis or labeled Explore Mode — and map each
family to its **owner pipeline**, so Ticket 20 relationship-freeze denominators
are not mixed with financial feature load paths.

Authoritative doctrine:

| Doc | Role |
| --- | --- |
| `CONTEXT.md` (Agent decision support) | Glossary: Decision Graph Bundle, Subject Feature Screen, As-Of features, coverage flags |
| `docs/adr/0001-agent-decision-surface-first.md` | Agent-first product; bundle unit; pure-SEC features |
| `docs/release-readiness/agent-and-research-source-relevance-windows.md` | Agent vs research windows; CAGR ≠ relationship load |
| `docs/release-readiness/relationship-source-coverage-by-document-type.md` | Per-form lookbacks for freeze inventory |
| `docs/data-architecture.md` | Pipeline inventory, silver tables, Branch A/B, MDM, gold |

## Two surfaces (do not conflate)

| Surface | Consumer | Truth | History needed |
| --- | --- | --- | --- |
| **Agent Decision Surface** | Trading agents; Human Audit View (Agent View Mode) | Watermark-aligned Snowflake Decision Contract only | Current-at-watermark edges + **declared** feature lookbacks as *inputs* to as-of rows |
| **Investment research / Explore** | Humans | Gold/graph under Explore labels; not agent-grade | May be wider; must not silently expand agent contract |

**Implication:** Multi-year financial history (companyfacts → CAGR inputs) is a
**feature pipeline** concern. Multi-year relationship document bulk-load (proxy /
8-K / 13F freeze) is a **Ticket 20 / relationship inventory** concern. Loading less
8-K or less 13F does **not** break 3y/5y CAGR.

---

## Master table — artifact families

| # | Family | Forms / source | Owner pipeline | Agent Decision Surface role | Explore / analysis role | Ticket 20 freeze denominator? |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Institutional holdings (13F)** | `13F-HR`, `13F-HR/A` | Branch B `bootstrap-fundamentals --mode thirteenf` → silver `sec_thirteenf_holding` → MDM `INSTITUTIONAL_HOLDS` → graph + gold `institutional_holdings` | Bundle sections `holders_of_subject`, `subject_as_manager_portfolio`; Latest Complete Holdings Period + lag in coverage | QoQ flow research, deep manager history | **Yes** — agent GO window `max(W−3y, 2013-05-20)`; floor `2013-05-20` only (XML era) |
| 2 | **Proxy employment / compensation** | `DEF 14A`, `DEF 14A/A`, `DEFA14A`, `PRE 14A` | Branch B `bootstrap-fundamentals --mode per-filing` (proxy) → `sec_executive_record` → MDM `EMPLOYED_BY` + gold `executive_records` | Bundle `employment` (source `proxy_def14a`); baseline officer set | Multi-year pay tables, historical officer rosters | **Yes** — latest definitive proxy ≤ W always + proxies ≥ `W−5y` |
| 3 | **Item 5.02 8-K employment events** | `8-K`, `8-K/A` with Item 5.02 or ambiguous items | Artifact load + `parsers/item_502.py` → employment events → MDM `EMPLOYED_BY` (source `item_5_02`) | Bundle `employment` temporal open/close | Recent C-suite change audit trails | **Yes** — filing date ≥ `W−1y` only |
| 4 | **Unrelated 8-K** (no 5.02) | `8-K`, `8-K/A` items prove non-5.02 | Not bulk-downloaded for relationship gate | Out of scope for employment | Optional Explore (earnings 8-K may still feed family 8) | **No** — `not_applicable` from metadata; not freeze candidates |
| 5 | **Insider ownership Form 3/4/5** | `3`, `4`, `5` (+ amendments) | Ownership parser policy / `parse-ownership-bronze` → `sec_ownership_*` → MDM `IS_INSIDER`, `HOLDS` → gold `ownership_*` | Bundle `insiders` (graph + gold accession) | Insider Watch, trade timelines | **Not Ticket 20 primary inventory** today; agent default window `W−2y` + current derived holds (product default until grilled) |
| 6 | **Companyfacts / XBRL financials** | SEC companyfacts API (10-K/10-Q concepts) | Branch B `bootstrap-fundamentals --mode entity-facts` → `sec_financial_fact` / `sec_financial_derived` / scores → gold `financial_*` | **As-Of Decision Features**, Subject Feature Screen; Primary Annual + Latest Interim | Explore factors, multi-period series, forensic scores | **No** — separate feature pipeline; **must not** enter relationship freeze denominators |
| 7 | **Earnings release 8-K** | `8-K` earnings / Item 2.02-style content | Branch B per-filing `EarningsRelease` → `sec_earnings_release` → gold | Optional feature input when pure-SEC; not relationship edges | Earnings research charts | **No** for relationship freeze (distinct from Item 5.02) |
| 8 | **ADV / private funds** | ADV Part 1 / IAPD (operator bronze) | Operator-placed bronze → `parse-adv-bronze` → `sec_adv_*` → MDM `MANAGES_FUND` + gold ADV tables | Issuer bundle: ADV **`not_applicable`**; manager bundles (ticket 12) when in scope | Adviser structure research | **Separate bulk path** (ticket 21 / IAPD), not Form 13F/8-K freeze; agent default current ADV + `W−2y` material changes if published |
| 9 | **Parent / Exhibit 21–8** | `EX-21*`, Form 20-F `EX-8*` | Parent-company contract (ticket 22); not current freeze forms set | Bundle `has_parent` when inventory complete | Org-structure Explore | **Separate** from Ticket 20 proxy/8-K/13F freeze; latest exhibit set as-of W |
| 10 | **Auditor evidence** | Audit report / PCAOB evidence | Auditor contract (ticket 23); DEI flags partial today | Bundle `auditor` | Auditor change research | **Separate** bulk/evidence path; agent wants latest as-of W |
| 11 | **Submissions / filing metadata** | Submissions JSON, daily index | Branch A bootstrap / daily-incremental → `sec_company_filing` | Inventory substrate for freezes; not a bundle section | Filing timelines | Prerequisite for freeze, not a freeze form family itself |
| 12 | **Reference tickers / universe** | `company_tickers*.json` | `seed-universe` / MDM seed | Decision Subject Universe = tracked/active only | Universe screens | No |

### Code form sets (relationship freeze builder)

From `edgar_warehouse/application/relationship_bulk_load.py`:

```text
PROXY_FORMS     = {DEF 14A, DEF 14A/A, DEFA14A, PRE 14A}  → EMPLOYED_BY
THIRTEENF_FORMS = {13F-HR, 13F-HR/A}                      → INSTITUTIONAL_HOLDS
EIGHT_K_FORMS   = {8-K, 8-K/A}                            → EMPLOYED_BY (Item 5.02 / ambiguous)
DEFAULT_COVERAGE_START = 2013-05-20   # currently global; product wants per-type windows
```

---

## Agent Decision Surface — how families land

### Decision Graph Bundle (Subject Bundle Read)

Unit of agent deep-dive (ADR 0001; `docs/subject-bundle-read.md`;
`edgar_warehouse/serving/subject_bundle_read.py`):

| Bundle section | Source families | Relationship / data |
| --- | --- | --- |
| `insiders` | Form 3/4/5 ownership | `IS_INSIDER` + gold ownership accession |
| `employment` | Proxy + Item 5.02 8-K | `EMPLOYED_BY` (`proxy_def14a` / `item_5_02`) |
| `holders_of_subject` | 13F | `INSTITUTIONAL_HOLDS` (managers holding subject) |
| `subject_as_manager_portfolio` | 13F | Subject’s own 13F book when applicable |
| `auditor` | Auditor evidence / flags | `AUDITED_BY` |
| `has_parent` | EX-21 / EX-8 | `HAS_PARENT_COMPANY` (registrant-disclosed) |
| `subject_features` | Companyfacts → gold factors | As-Of pure-SEC feature vectors |
| `adv` | ADV (issuer) | Always `not_applicable` on pure issuer bundles |

Default edges: **Current Neighborhood** at watermark; Neighborhood History optional.

### Subject Feature Screen

Flat rank/filter over Decision Subject Universe (`docs/subject-feature-screen.md`;
`edgar_warehouse/serving/subject_feature_screen.py`):

- **Inputs:** gold financial period/factor rows (family 6), not full neighborhoods.
- **Shape:** Primary Annual (FY) + optional Latest Interim if newer `period_end`.
- **Null semantics:** null ≠ zero.
- **Not:** 13F history dumps, free gold joins labeled as the screen.

### Eleven required MDM relationship types (generation scope)

From `docs/release-readiness/relationship-eligibility-at-release-watermark.md`:

`IS_INSIDER`, `HOLDS`, `COMPANY_HOLDS`, `ISSUED_BY`, `IS_ENTITY_OF`, `IS_PERSON_OF`,
`MANAGES_FUND`, `HAS_PARENT_COMPANY`, `EMPLOYED_BY`, `AUDITED_BY`, `INSTITUTIONAL_HOLDS`.

Ticket 20 bulk-load gate focuses on **source candidates for `EMPLOYED_BY` and
`INSTITUTIONAL_HOLDS`** (proxy + Item 5.02 8-K + 13F). Other types have separate
contracts/tickets (ADV 21, parent 22, auditor 23) or use ownership/silver paths
already on the normal bootstrap.

---

## Pipeline ownership (bulk-load path summary)

```text
SEC EDGAR
  ├─ Branch A (submissions + artifacts) ──→ sec_company_filing, bronze filings
  │     ├─ ownership policy (3/4/5) ──────→ sec_ownership_* ──→ IS_INSIDER / HOLDS
  │     └─ Ticket 20 strict freeze ──────→ selected proxy / 8-K 5.02 / 13F only
  │
  ├─ Branch B entity-facts (companyfacts) → sec_financial_* ──→ gold features / Screen
  ├─ Branch B per-filing (earnings, proxy)→ sec_earnings_release, sec_executive_record
  ├─ Branch B thirteenf ─────────────────→ sec_thirteenf_holding
  │
  ├─ Operator ADV bronze ────────────────→ sec_adv_* ──→ MANAGES_FUND (ticket 21 path)
  │
  └─ MDM derive/export/sync-graph ───────→ Snowflake graph + Decision Contract projection
         gold-refresh ───────────────────→ EDGARTOOLS_GOLD (+ feature rows)
```

| Owner path | Families | Entry points (docs/code) |
| --- | --- | --- |
| **Relationship freeze (Ticket 20)** | 13F, proxy, Item 5.02 8-K | `relationship_bulk_load.py`, `docs/release-readiness/required-relationship-bulk-load-completion-gate.md`, `ticket20-strict-bulk-load-resume.md` |
| **Companyfacts / gold features** | Financial facts, derived, factors | `bootstrap-fundamentals --mode entity-facts`, `parsers/financials*.py`, dbt `financial_*.sql` |
| **Ownership parse** | Form 3/4/5 | `parsers/ownership.py`, `parse-ownership-bronze`, gold `ownership_*` |
| **ADV** | Adviser / funds | `parsers/adv.py`, `parse-adv-bronze`, ticket 21 IAPD |
| **Parent / auditor** | EX-21, audit evidence | release-readiness contracts (tickets 22–23) |
| **Contract serving** | Bundle + Screen | `edgar_warehouse/serving/*`, `infra/snowflake/sql/decision_contract/` |

---

## Families that must **not** mix into Ticket 20 freeze denominators

These must **never** be counted in relationship bulk-load completion ledgers or
`coverage_by_document_type` freeze math as if they were proxy/8-K/13F candidates:

1. **Companyfacts / XBRL / financial feature history** — CAGR, growth, earnings-potential
   inputs; Subject Feature Screen rows.
2. **Derived gold metrics and forensic scores** (`sec_financial_derived`, accounting flags).
3. **Earnings-only 8-Ks** and other non–Item 5.02 8-Ks (metadata `not_applicable` for employment).
4. **Full historical 8-K corpus since 2013** — product window is **1 year** for Item 5.02.
5. **Pre-XML 13F** (before `2013-05-20`) — format floor, not loadable claim.
6. **Optional deep Explore archives** (13F full XML-era to 2013 when agent only needs 3y;
   proxies older than baseline+5y except the single baseline) — separate pipeline if at all.
7. **ADV/IAPD bulk**, **EX-21 parent inventory**, **auditor evidence inventory** — own gates,
   not the Ticket 20 Form 13F/proxy/8-K freeze.
8. **Text projections**, daily index rows, ticker reference snapshots as “relationship sources.”
9. **Market prices / PE / market cap** — outside Pure-SEC Decision Features entirely.

Also: do **not** couple financial CAGR completeness to 13F or 8-K document counts
(`agent-and-research-source-relevance-windows.md` grill #3).

---

## Agent-useful windows (product-confirmed, for later tickets)

Relative to Release Data Watermark `W` (from release-readiness docs; exact lock
is subsequent tickets 03–11 on this map):

| Family | Agent-relevant from | Notes |
| --- | --- | --- |
| 13F | `max(W−3 years, 2013-05-20)` | Floor is format; full-to-2013 optional Explore |
| Proxy | Latest definitive ≤ W + ≥ `W−5y` | Baseline may predate 5y band |
| Item 5.02 8-K | `W−1 year` | Unrelated 8-K out of scope |
| Form 3/4/5 | Default `W−2 years` + current holds | Until product overrides |
| Financial features | 3y/5y FY **inputs** to as-of row | Not freeze documents |
| ADV | Current + default `W−2y` material changes | Separate path |
| Auditor / parent | Latest as-of W | Separate contracts |

---

## Pointer index (repo)

| Need | Location |
| --- | --- |
| Agent glossary | `/Users/aneenaananth/.grok/worktrees/projects-edgartools-platform/explore/CONTEXT.md` |
| ADR Decision Surface | `docs/adr/0001-agent-decision-surface-first.md` |
| Windows + agent vs research | `docs/release-readiness/agent-and-research-source-relevance-windows.md` |
| Per-document coverage | `docs/release-readiness/relationship-source-coverage-by-document-type.md` |
| Ticket 20 gate | `docs/release-readiness/required-relationship-bulk-load-completion-gate.md` |
| Relationship eligibility | `docs/release-readiness/relationship-eligibility-at-release-watermark.md` |
| Data pipelines | `docs/data-architecture.md` |
| Bundle section contract | `docs/subject-bundle-read.md` |
| Feature screen contract | `docs/subject-feature-screen.md` |
| Freeze inventory builder | `edgar_warehouse/application/relationship_bulk_load.py` |
| Parsers | `edgar_warehouse/parsers/{ownership,thirteenf,proxy_fundamentals,item_502,adv,financials,earnings_release}.py` |
| Serving | `edgar_warehouse/serving/{subject_bundle_read,subject_feature_screen,decision_contract}.py` |
| Gold models | `infra/snowflake/dbt/edgartools_gold/models/gold/` |
| ADV / parent / auditor contracts | `docs/release-readiness/{adviser-fund,parent-company,auditor-evidence}-*.md` |

---

## Exit criteria checklist

- [x] Table of artifact families with owner pipeline and agent vs Explore role.
- [x] Explicit list of families that must **not** mix into Ticket 20 relationship freeze denominators.
- [x] Pointers into repo docs/code for each family.
