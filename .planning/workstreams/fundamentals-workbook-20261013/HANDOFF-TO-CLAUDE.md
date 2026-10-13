# Fundamentals acquisition requirements: handoff to Claude

Owner handing over: Codex. Branch: `codex/fundamentals-workbook-requirements-20261013`.
Source: `Financial-Model-and-Valuation-Template.xlsx`; source hash in `EVIDENCE.json`.
User requested a data requirements list, then a PR and handoff to Claude.

## Delivered

All seven worksheets, shared formulas, comments, defined names and drawing notes
were read. The catalog has 115 grouped entries: 58 acquisition entries, 19 model
assumptions, 24 computed outputs and 14 context/provenance entries. These counts
are grouped requirements, not a promise of 115 individually available source facts.
`DATA-REQUIREMENTS.md` is the reading path; CSV/JSON retain full source-route,
priority and note columns. The separate requirements Excel is committed here and
also available at `/Users/aneenaananth/Downloads/Fundamentals-Acquisition-Requirements.xlsx`.
The original source workbook stays unchanged and is not committed.

## Next planning steps

- Reconcile this catalog with the existing Company financials acquisition map;
  preserve its all-years history/CAGR scope. Five fiscal years, 20 quarters plus
  annuals and opening positions are this template's minimum window, not a new cap.
- Measure standard entity-wide Company Facts coverage, then identify filing/iXBRL/
  notes/IR supplementation for custom concepts, revenue dimensions and tax details.
  Source routes and exact taxonomy mappings remain unqualified candidates.
- Define fiscal periods, as-reported versus restated vintage selection, standalone
  quarter derivation, units/currency and basic/diluted/outstanding shares explicitly.
- Resolve `GAPS.json` before using the workbook calculations in production. In
  particular: reported CFO/CFI/CFF versus modeled cash flows; D&A overlap; monetary
  common-stock balances versus shares; omitted APIC; DCF cash-flow basis, bridge,
  five-period terminal discounting, and its forecast-Q1 share denominator.
- Use configuration for fields/rules and the Rust core with Python callers/custom
  code. Preserve hashes, bounds, transaction/concurrency checks and recovery.

## Boundary

This handoff authorizes Claude to review and incorporate the requirements into
planning. It does not qualify or activate a financials feed, resume live SEC
acquisition, choose financial assumptions, approve mappings, or deploy AWS tasks.
Live SEC qualification remains parked until the explicitly approved AWS Step
Functions rollout qualification. No runtime/skill instructions or shared active
workstream files were changed by this task.
