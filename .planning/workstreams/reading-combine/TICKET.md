# Configured reading combination

Parent goal: self-sustaining skills, installed Rules creator, orchestration of configured parsing and MDM, custom steps only for demonstrated gaps, and complete old-parser retirement. Base cc5b1332. Full scope remains active.

- [x] Inspect live refs/CI, worker interfaces and Company collection logic — preserved shared dirty checkout; GoF review of worker history supports plain functions with a registered profile, 2026-10-04 17:04 ET.
- [ ] Implement bounded generic grouping and joins over immutable reading receipts, with explicit ordering, uniqueness, missing policies and row checks.
- [ ] Verify identity/type separation, changed receipts, refused inputs, ordering and no partial writes.
- [ ] Qualify Company form/ticker/address collection against retained functions, including adversarial cases.
- [ ] Prove installed read → combine → prepare → merge on PostgreSQL 16 with separate worker/verifier roles.
- [ ] Document installed profile and configured grammar in bundled skills.
- [ ] Obtain independent Standards/GoF and Spec reviews, resolve findings, and full CI.
- [ ] Commit/push/open a reviewable PR with evidence.
- [ ] Finish full Company preparation/census/provenance, GLEIF streaming, configured acquisition, adapter replacement, old-reader deletion and full installed population/replay in the parent goal.

Design: source.combine reads bounded, hash-verified configured readings; generic key grouping and declared joins. No loader imports, source-specific callbacks, implicit field overwrite or ambient reference discovery. Independent verifier rebuilds exact bytes. Bookkeeping remains profile/task control only.
