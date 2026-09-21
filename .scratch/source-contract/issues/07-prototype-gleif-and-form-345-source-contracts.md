# Prototype the GLEIF and Form 3/4/5 Source Contracts

Type: prototype
Status: resolved (2026-09-21)
Blocked by: 04, 05, 06

## Question

Does the language hold on real sources? Write both Source Contracts with
fixtures and tests, a throwaway local runner, and the generated Mapping
Document. Measure against the acceptance checks: files changed per source,
contract length, custom fraction, and whether the Form 3/4/5 contract
reproduces `ownership.py`'s silver rows on local bronze.

## Note before starting

Codex is building a native GLEIF source on `codex/company-native-gleif`
(`.scratch/handover/2026-09-20-codex-policy-language-reconciliation.md`),
reading the JSON ZIP Golden Copy. Read that work first: the GLEIF Source
Contract here is a throwaway prototype and must not compete with Codex's
loader. Use Codex's paths and fixtures where they exist.

## Answer

**The language holds on both real sources.** Prototype and full results:
[prototype/README.md](../prototype/README.md).

- **Form 3/4/5** reproduces `edgar_warehouse/parsers/ownership.py` on
  **5,356 / 5,356** local bronze artifacts, with 0 unexpected differences
  against [expected-differences.md](../prototype/expected-differences.md),
  which was written before the run. 5 named cases pass. The gate passed over
  all 5,356 artifacts (5,743 owner and 10,964 transaction rows, 15 s) with 0
  rejects and 0 violations. 2 of 60 columns are custom (3.3%).
- **GLEIF Level 1** is 93 lines including tests, 0% custom. It proves over
  316 real records, with one declared exception carrying its `why:`. One merge
  case runs through Clean MDM's real Merge Stage in a throwaway Postgres 16:
  a seed is bound by a declared Steward decision, and an unbound record waits
  for binding. Planted wrong expectations all fail.
- Checks 2, 3, 4, 6, 8, 9, 10 and 11 were exercised literally.
- The as-of lookup was proven on a synthetic dated layout only, because the
  local copy is flat. The path date is the fetch date by construction.

Eleven findings go to the spec (README "Findings"). The one that needs Codex:
**the adapter needs a kind per row at mapping time, but rule C-J is a policy
classification**. The prototype used a declared custom step as a stand-in.
Limits: no streaming-zip GLEIF reader, and the Rules Database is a folder of
proofs (no save/export/approval).
