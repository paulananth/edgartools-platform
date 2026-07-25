# 03 — Pure-SEC vs market boundary for ER

Type: grilling  
Status: resolved  
Blocked by:  

## Question

Given ADR 0001 (pure-SEC Decision Features; no price/mcap/PE in that vector): for ER skills that need WACC/PT/trading setup, do we (a) keep market data **External only**, (b) add a **separate** gold MARKET surface outside pure-SEC features, or (c) revise ADR 0001? Document the join rule ER agents must follow.

## Answer

**Accepted: (a) for phase-1 + (b) as documented future option — do not revise ADR 0001.**

### ERDP-06 (locked)

1. **ADR 0001 stands.** Pure-SEC Decision Features and Agent-Grade Subject Bundle / Feature Screen **must not** include price, market cap, PE, EV, or equivalent market fields.

2. **Phase-1 market data = External only.** ER skills join firm/vendor prices (or optional non-product `market/` helpers) **outside** the Decision Contract. No phase-1 gold MARKET product (consistent with ticket 01).

3. **Phase-2 option (not in ERDP-01…06 build list):** A **separate** Gold **Explore** MARKET surface (e.g. daily close, mcap, beta) may be added later. It must:
   - Live outside pure-SEC feature vectors and Agent View Mode contract payloads
   - Join by ticker/CIK + as_of date
   - Never be promoted into `subject_features` without a new ADR

4. **Join rule for ER agents:**

```text
Agent-Grade read  → Decision Watermark + pure-SEC surfaces only
                    (financials, filings, ownership, graph neighborhood, …)

Valuation / PT / trading setup
                  → External market (phase-1) or future Gold MARKET Explore (phase-2)
                  → Join: ticker|CIK + as_of
                  → Do not claim Agent-Grade on mixed price-in-features payloads
```

5. **Option (c) rejected:** no ADR 0001 revision for v1/phase-1.
