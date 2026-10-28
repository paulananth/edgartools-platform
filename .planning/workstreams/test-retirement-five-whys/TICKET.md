# Retire redundant tests using five whys

Status: in progress
Baseline: origin/main `0a1470c1a`; repository-wide Python collected cases. Native Rust cases are inventoried separately. Original target: 75%; operator clarified “Retire only proven redundancy” after the first measured pass; no deselection, assertion packing, or skipped tests counted as retirement.

## Parts

- [x] Inventory collected cases, test functions, CI execution and overlap — 2026-10-27 19:40 ET: 4,262 error-free collected cases; original target 3,197; prospective guard passes eight candidate paths; baseline and denominator recorded in FIVE-WHYS.md.
- [x] Apply five whys to candidate families — 2026-10-27 19:40 ET: six family decisions in FIVE-WHYS.md, all 127 retired IDs mapped in retirement.json; zero missing replacements; operator clarified that distinct coverage is retained.
- [x] Remove justified redundant tests and stale wrapper code — 2026-10-27 19:40 ET: collection 4,262 → 4,135; 126 duplicate scenario invocations and one identical classification body; scenario assertions, installed matrix and production code unchanged, verified by AST and git diff.
- [x] Verify retained behavior and collection counts — 2026-10-27 19:42 ET: testmon 49 affected classification/architecture checks, 30 retained caller cases on PostgreSQL (124 seconds) and 30 on MySQL (177 seconds); retained classification rejects an injected wrong verdict; collection 4,135; no CI speedup claimed.
- [ ] Review Standards, Spec and GoF; publish the change in a PR and verify final CI with a bounded watcher.
- [x] Learning → skill: none — 2026-10-27 19:40 ET: existing mdm-engineering cheapest-proof and independent-installation guidance applies; no missing procedure demonstrated.

## Method

1. Why does the test exist? Name its exact failure.
2. Why does that failure matter? Name the observable consequence.
3. Why is this path needed now? Trace its current caller or supported contract.
4. Why is this test the required proof? Identify equivalent retained proof and whether it exercises the same boundary.
5. Why keep it after that comparison? Keep unique behavior; retire only when the current obligation is absent or another retained test proves it.

The percentage is a requested target, not evidence that tests are redundant. Unique database guarantees, authorization, failure recovery and exact value handling need executable proof. Record any shortfall and its reasons.
