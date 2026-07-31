# Use a bounded canonical SEC ticker resolver

Type: grilling (HITL)
Status: resolved

## Question

Which bounded source should resolve a ticker such as `AAPL` into the dashboard's
canonical subject before tab-specific queries run?

## Answer

The user confirmed a bounded canonical SEC company-ticker snapshot read view.
It resolves ticker, company-name, and CIK input into a canonical CIK (or bounded
disambiguation choices). The current empty `EDGARTOOLS_GOLD.TICKER_REFERENCE`
export is not an acceptable dependency for dashboard symbol lookup.

This resolver is a UI lookup seam only. It does not claim that financial, insider,
or agent-ready data exists for the resolved issuer.
