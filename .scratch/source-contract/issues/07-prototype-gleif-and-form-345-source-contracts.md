# Prototype the GLEIF and Form 3/4/5 Source Contracts

Type: prototype
Status: open
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
