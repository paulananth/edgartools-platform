# Configured reading combination

Parent goal: self-sustaining skills, installed Rules creator, orchestration of configured parsing and MDM, custom steps only for demonstrated gaps, and complete old-parser retirement. Rebased on merged main 92ace35a; retains #817 guidance and #818 object trial. Full scope remains active.

- [x] Inspect live refs/CI, worker interfaces and Company collection logic — preserved shared dirty checkout; GoF review of worker history supports plain functions with a registered profile, 2026-10-04 17:04 ET.
- [x] Implement bounded generic grouping and joins over immutable reading receipts, with explicit ordering, uniqueness, missing policies and row checks — verified 39 focused cases, ordered multiple-reading selection and text receipt keys; 2026-10-04 17:40 ET.
- [x] Verify identity/type separation, changed receipts, refused inputs, ordering and no partial writes — focused tests passed, including eager filter validation regression; 2026-10-04 17:40 ET.
- [x] Qualify Company form/ticker/address collection against retained functions, including adversarial cases — four explicit fixture tests passed; raw address derivation and full Company remain outside this evidence; 2026-10-04 17:40 ET.
- [x] Prove installed read → combine → prepare → merge on PostgreSQL 16 with separate worker/verifier roles — all eleven local installed modes completed; CI engine 238 passed/no skips, including combined-records; 2026-10-04 17:45 ET.
- [x] Document installed profile and configured grammar in bundled skills — command/link discovery returned no unresolved instructions; both review axes passed; 2026-10-04 17:40 ET.
- [x] Obtain independent Standards/GoF and Spec reviews and resolve findings — both final reviews report no scoped blockers at 901b63a5; original filter defect fixed/tested; 2026-10-04 17:40 ET.
- [x] Verify every suite and aggregate CI gate on the reviewed code — run 37236974353 at 901b63a5: 1,660 Python passed, one existing xfail, no skips; 70 Rust passed; 2026-10-04 17:45 ET. Final evidence commit requires its own CI recheck before PR readiness, tracked in PR #819.
- [x] Commit/push/open a reviewable PR — draft #819 at 901b63a5; qualification and final CI pending; 2026-10-04 17:40 ET.
- [x] Qualify 1,000 receipt-pinned captures and record exact recent-form evidence and limits — qualification.json: 107,197 filing rows, 500 source.read and 63 source.combine units, exact forms match in 228.355 seconds; pagination/full Company remain false; 2026-10-04 17:41 ET.
- [ ] Finish full Company preparation/census/provenance, GLEIF streaming, configured acquisition, adapter replacement, old-reader deletion and full installed population/replay in the parent goal.

Design: source.combine reads bounded, hash-verified configured readings; generic key grouping and declared joins. No loader imports, source-specific callbacks, implicit field overwrite or ambient reference discovery. Independent verifier rebuilds exact bytes. Bookkeeping remains profile/task control only.

Initial installed trial refused structured unit keys before submission (224 passed, 1 failed in 384.09 seconds). Corrected the worker/fixture to URI and SHA256 text keys without changing Bookkeeping; full committed-head rerun in progress.

## Final verification and limits

- Full CI [37236974353](https://github.com/paulananth/edgartools-platform/actions/runs/37236974353): Unit 402, Architecture 251, MDM 512, Integration 257 plus one existing xfail, Engine 238; Rust 70. All suites and aggregate passed; no skips.
- Local committed-head full engine: 236 passed, two merged object tests failed because PYTHONPATH selected the pre-object native binding; 441.77 seconds (7m22). All eleven installed pipeline trials passed using their freshly built installed binding. With the current object binding, both failures and the 39 combination/Company tests passed together: 41 passed in 3.14 seconds. No test or production contract was weakened.
- Offline qualification: 1,000 distinct main captures, 107,197 recent filing rows, 500 read and 63 combination units, exact recent-form matches; 228.355 seconds. Stored report is fixture-specific evidence, not paginated history or installed full Company population proof.
- Net +40 Python cases (35 combination, four Company fixture comparisons, one installed mode), zero deletions; Rust unchanged at 70. No speed claim.
- Parent goal remains incomplete: full Company preparation/census/provenance and pagination, GLEIF streaming, configured acquisition, adapter replacement, retained-parser deletion, full installed population/replay.
