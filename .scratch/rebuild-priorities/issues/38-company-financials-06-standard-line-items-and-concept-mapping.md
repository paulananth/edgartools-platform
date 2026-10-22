# 06 The standard line items and how concepts map to them

Priority: 38, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/06-standard-line-items-and-concept-mapping.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: resolved (2026-10-21 21:16 ET, operator rulings below). Blocked by: 35, 37. Map: [map](../../company-financials/map.md).

## Question

Which standard line items does silver carry (from ticket 01's measures), and by what rule does each come from reported concepts: an ordered list of concepts per line item, first present wins, or a sum of parts? Is the mapping rules configuration (a reading or combine contract) or a custom step, and how does a Company with none of a line item's concepts show (empty and counted, never guessed)?

Starting point: research section 6 (nineteen line items, ordered concept lists, chosen per company and period; never a nearby period; the chosen concept and accession recorded). Check first the 7 filers whose `Revenues` is below contract revenue, and the cohort coverage of the three uncounted concepts (`NetIncomeLossAttributableToNoncontrollingInterest`, `MinorityInterest`, `TemporaryEquityCarryingAmountAttributableToParent`).

## Checklist

- [x] Measure the checks the question names on the captured cohort (2026-10-21 21:12 ET; counts in the research note below) (2026-10-21 21:16 ET)
- [x] Outside standards researched on the operator's instruction ("again use standards from external vendors keep this reserch handy for other decssions"): [research 02](../../company-financials/research/02-vendor-standards.md) (2026-10-21 21:16 ET)
- [x] Revenue when `Revenues` is smaller than contract revenue (operator: "Standard order + a quality check (Recommended)") (2026-10-21 21:16 ET)
- [x] Where the map lives (operator: "Rules configuration (Recommended)") (2026-10-21 21:16 ET)
- [x] Learning → skill: `skills/data-modeling/SKILL.md`, "6. A transaction part" (a standard line item from many reported concepts) and Hard stops (outside standards before a domain rule); `CLAUDE.md`: macOS has no `timeout` for a watcher deadline (2026-10-21 21:19 ET)

## Answer

1. **Nineteen line items**, as research 01 section 6 lists them. Where its concept order differs from the public standard (Fundamental Accounting Concepts' Try Order), the standard's order wins, following the operator's ruling to use outside standards: cost of revenue tries `CostOfRevenue` first, then `CostOfGoodsAndServicesSold`, `CostOfServices`, `CostOfGoodsSold`.
2. **The rule per line item:** for each company and annual period, the first concept in the list that has a fact for that exact period wins, using the latest-filed copy (ticket 35). An annual period is 364–371 days (ticket 35), replacing research 01's 350–380. The chosen concept and accession are recorded beside the value.
3. **Computed fallbacks** (the standard's impute rules: net income = `ProfitLoss` − NCI; parent equity = equity including NCI − `MinorityInterest`; gross profit = revenue − cost of revenue; liabilities from liabilities and equity; total debt from its parts) are allowed only where research 01 lists them, and each value carries the flag "computed". The three concepts they need are used in the cohort: NCI net income by 133 filers, `MinorityInterest` by 139, temporary equity by 55.
4. **Revenue:** the standard order (`Revenues` first). A data-quality rule flags any period where the chosen revenue is smaller than another revenue total filed for the same period (21 periods of 13 filers in the cohort), for a steward. No silent switch.
5. **A missing line item** is empty, with the reason "no concept filed", and counted per line item; never a nearby period, never a guess.
6. **The map is rules configuration:** a reviewed YAML file under `rules/` names each line item, its concepts in order, any computed fallback and its flag; a configured step applies it. An operation the engine lacks (such as "first present in order" across rows) is added by the build ticket (46) as a generic engine primitive. A change to the map is a reviewed rules change with a test.
7. USD only, until ticket 42 (currencies and IFRS) rules otherwise.
