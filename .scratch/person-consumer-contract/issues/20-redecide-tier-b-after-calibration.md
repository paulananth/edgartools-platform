# Re-decide Tier B now that it has been measured

Type: grilling
Status: open
Blocked by: none (17 resolved 2026-09-20)

## Question

[Research 17](../research/17-tier-b-context-key-calibration.md) measured
ticket 02's Tier B key on 921 labelled pairs and found its stated home and
its measured home are opposite. Ticket 02 stands except where this ticket
amends it; four things need an operator decision:

1. **Scope.** Tier B is defined for "a record whose cross-reference ids are
   all unbound" — true for ~0.3% of ADV rows and 0% of Form 3/4/5 rows.
   On id-bearing sources the residual it decides is **1 same / 27 different**
   (precision 0.018). Does Tier B stop applying to id-bearing sources
   altogether (same name + same firm + *different* ids ⇒ Tier C or an
   explicit "different person" prior), or keep applying with a veto?
2. **The bar.** Pooled name-only (8-K + DEF 14A), `mi` variant: 269/269 with
   8 unsettled, **LCB95 0.99033 — clears 99%**; LCB97.5 0.98632 — does not.
   The Mastering Policy spec already flags this 95%/97.5% mismatch as an
   item for Codex. Accept at one-sided 95% and ship, or label the 104
   further pairs research 17 says exist and clear 97.5% too?
3. **The key's fields.** Research 17 says: drop "consistent role/flag" from
   the key (it rejects 33 same-person pairs and catches 10 the name already
   catches; keep it as evidence); make a **generational suffix a hard veto,
   not a normalization step** (11 of 166 homonym pairs are father/son
   separated only by `JR`/`III`); and match a middle initial to a middle
   name (`mi`, not `full`). Adopt all three?
4. **DEF 14A eligibility.** 58.7% of its rows are not person names
   ([ticket 10](10-fix-proxy-executive-name-parser-leak.md)). Its own n is
   51 (LCB95 0.9496). Does the pooled figure carry proxy, or does proxy
   stay ineligible until the parser is fixed and re-measured on its own?

Whatever is decided replaces ticket 02 §4's Tier B row and feeds the
Person Q11 amendment already with Codex.
