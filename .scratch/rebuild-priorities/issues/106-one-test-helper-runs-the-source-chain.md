# One test helper runs the read, combine and prepare chain

Priority: 106, tier 4, housekeeping. Map: [Rebuild priorities](../map.md).

Type: task (tests only). Status: done (#1054 merged 2026-10-17 14:07 ET). Blocked by: none. Raised by: 80 (Onboard OpenFIGI with the skills), GoF finding 1 of its first review, 2026-10-17.

## Why

Four integration tests each carry their own copy of the steps that run configured rules over invented files: put a manifest, run `source_read` and verify it, run `source_combine` and verify it, run `mdm_prepare` and verify it, then normalize the prepared lines:
- `tests/integration/test_adv_custodian_link.py`
- `tests/integration/test_nport_link_start.py`
- `tests/integration/test_nport_isin_link.py`
- `tests/integration/test_openfigi_security.py`

The copy was repeated by #1022, #1025, #1030 and #1046, so the next onboarding test will copy it a fifth time, and a change to a worker's task shape is a change in four places.

## Checklist

- [x] GoF consult on the four copies: evidence of repeated change (four PRs each added a copy); the shared part is running each worker with its verifier and normalizing the prepared lines; manifests, contexts, lookups and keys differ per test and stay there. Extract functions, no classes (2026-10-17 13:56 ET)
- [x] `tests/support/source_chain.py`: `read`, `combine`, `prepare` (each asserts its worker's verifier) and `records` (normalize; optionally keeps refused records by key) (2026-10-17 13:56 ET)
- [x] The four tests use it: 120 lines removed, 37 added; every verifier assertion now lives in the helper, each test's own assertions unchanged; 10 tests pass (2026-10-17 13:56 ET)
- [x] Three-axis review (Standards, Spec, GoF): no change in behaviour, no verifier assertion dropped; fixed: the prepare check named by `mdm_prepare.CHECK`, `refused` and `key` asserted to go together, one continuation line aligned; GoF leave it (plain functions; the N-PORT `combine` binds its folder for two tests). 10 tests pass (2026-10-17 13:59 ET)
- [x] PR, CI green, merged on green: #1054, merged on green 2026-10-17 14:07 ET
- [x] Learning → skill: `skills/data-onboarding/SKILL.md` **test**: a test over invented files runs the rules through `tests/support/source_chain.py`, never a copy (2026-10-17 13:56 ET)
