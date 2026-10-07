# Replace SEC Company and Person mapped-value extraction

Parent: complete self-sustaining skill bundle/Rules creator, parsing and MDM orchestration, and complete old-parser retirement. Dependent on PR #857. Local qualification only; no deployment, activation or SEC requests.

- [x] Create isolated branch/tree from 16b1c19c and inspect existing adapters/source definitions and history. GoF: existing native interpreter and plain functions support the same measured field shape; no new hierarchy (2026-10-07 18:54 ET).
- [x] Bundle frozen native Company/Person field and matching recipes; 89 projection cases prove exact values/refusals, explicit null validation and missingness (2026-10-07 19:11 ET).
- [x] Verify complete assertion IDs, quality, classification and identity deferrals: 694 MDM/projection cases plus final pinned 2,000 captured comparisons in 35.109s (2026-10-07 19:11 ET).
- [ ] Verify installed restricted PostgreSQL publication/recovery, independent review and full CI; publish separate change.
- [ ] Remove remaining legacy record mapping with frozen-version replay evidence; retire Company preparation/census/provenance and GLEIF release/semantic consumers; prove whole-source census and installed 6,414 Company / 3,052 CIK+LEI population/recovery; finish parent L3–L8. These remain required for full goal completion.

- [x] Measure and resolve legacy census input boundary: unrelated Parquet-derived datetime metadata made whole-row JSON serialization fail. Declared input_fields excludes only unrelated roots, preserves selected types/missingness, validates bounds and covers all mapped paths; 125 affected cases passed in 8.06s (2026-10-07 19:01 ET).
- [x] Compare 1,000 authenticated SEC main captures for each source: 2,000 exact field/quality/assertion/refusal comparisons, 65 Company and 386 Person assertions; all other classification deferrals identical. Qualification passed in 33.855s; native/main/contract/helper/Rules/capture pins in captured-field-parity.json. Company main-derived scope excludes complete preparation (2026-10-07 19:03 ET).

- [ ] Extend installed restricted PostgreSQL proof to regenerate Company/Person assertions from raw fixtures inside the installed bundle before publication, recovery and duplicate replay; host assertions serve only as an oracle.

- [x] Fix independent standards review finding: selected tuples/non-string dictionary keys are refused before serialization; 698 MDM/projection cases passed in 19.36s and final 2,000 captured comparisons in 48.068s with refreshed helper pins. Reviewers confirmed zero remaining scoped blockers (2026-10-07 19:11 ET).
