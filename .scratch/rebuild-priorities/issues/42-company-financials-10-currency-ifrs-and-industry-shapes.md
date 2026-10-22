# 10 Currencies, IFRS filers and industry statement shapes

Priority: 42, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/10-currency-ifrs-and-industry-shapes.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: resolved (2026-10-22 07:51 ET, operator rulings below). Blocked by: 37. Map: [map](../../company-financials/map.md).

## Question

The cohort has non-USD units (`NetIncomeLoss` in CAD for 2 filers, EUR for 1; `Revenues` in AFN for 1) and 6 filers using `ifrs-full`; banks, insurers, REITs and utilities report revenue and debt differently (research section 6, items 1 and 12). Rule: USD only with others counted and listed, or carried in their own currency with the currency beside the value? IFRS concepts mapped, or listed as not covered? Industry concepts flagged by kind, or held apart?

## Checklist

- [x] Outside standards researched first (Compustat `curcd` and its Industrial and Financial Services formats, FactSet's reporting-currency option, Bloomberg's currency override, Compustat Global for IFRS): research 02 section 5 (2026-10-22 07:51 ET)
- [x] Cohort measured (counts only): research 02 section 5 (2026-10-22 07:51 ET)
- [x] Currency (operator, 2026-10-22: "Reporting currency + code (Recommended)") (2026-10-22 07:51 ET)
- [x] IFRS (operator: "Map into same items (Recommended)") (2026-10-22 07:51 ET)
- [x] Industry shapes (operator: "Same items, flagged by kind (Recommended)") (2026-10-22 07:51 ET)
- [x] Learning → skill: `skills/company-financials/SKILL.md`, "Currencies, IFRS and industry formats" (2026-10-22 07:51 ET)

## Answer

1. **Reporting currency with its code.** Silver keeps each figure in the currency it was filed in, with its ISO currency code beside it, as Compustat (`curcd`), FactSet (its reporting-currency option) and Bloomberg do. Nothing is converted. A measure is computed within one currency; one whose inputs mix currencies is null with the reason "mixed currencies". USD conversion needs an exchange-rate source, a new data provider, so it waits for its own ticket and permission. This replaces ticket 38's "USD only until ticket 42".
2. **IFRS mapped into the same line items.** Each of the 19 line items gains an ordered `ifrs-full` concept list beside its `us-gaap` list in the same rules YAML, as Compustat Global standardizes IFRS filers into its one item set. A filer is read from the taxonomy it files in; the value names its concept, so its taxonomy. The 6 IFRS filers (2 IFRS only) are proved against the answer key (ticket 44).
3. **One item set, flagged by kind.** Every filer gets the same 19 line items. A value from an industry concept carries its kind (bank, insurer, REIT, utility), as ticket 38 began. Each filer has a statement format, industrial or financial services, as Compustat keeps two (`INDL`, `FS`). The format follows from the Company's SIC code: 6000–6199 (banks and credit) and 6300–6411 (insurers) are financial services. A measure that means nothing for financial services (gross margin, ROIC, total debt and the ratios built on it) is null with the reason "not meaningful for financial services". Separate bank and insurer item sets wait for a later ticket.
