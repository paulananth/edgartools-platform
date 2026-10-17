# Shared configured source traversal

Type: task
Status: claimed

Spec: [agreed design](../spec.md). Base: `c997b860`.

## Parts

- [x] Inspect current main, dedicated branch/worktree, caller policies, history and GoF costs (read-only review; 2026-10-17 15:13 ET). Plain extraction around existing native engines; no hierarchy.
- [x] Establish affected testmon baseline (150 passed in 33.74s; 2026-10-17 15:17 ET).
- [x] Implement/test the shared traversal interface with existing framing and archive policies. (compiled private policy, JSON/XML/delimited and whole-archive seam cases passed; 2026-10-17 15:19 ET).
- [x] Migrate extraction and attestation; remove duplicated dispatch/EOF mechanics. (59 initial caller cases passed; neither caller retains archive/scanner dispatch; 2026-10-17 15:19 ET).
- [x] Verify corruption, counts, bounds, empty context, cancellation and contract immutability. (173 affected cases passed in 4.31s; original refusal/EOF suites retained; 2026-10-17 15:19 ET).
- [x] Preserve worker/verifier receipts, multi-input publication barrier and six attestation reports. (existing stream/XML/attestation and confirmation suites passed; 2026-10-17 15:19 ET).
- [x] Prove traversal edits alter all affected runtime fingerprints. (both caller digests change on traversal-byte edits; qualification uses attestation-owned dependencies; 2026-10-17 15:19 ET).
- [ ] Run affected type/architecture/integration and installed-package checks.
- [ ] Review Standards, Spec and GoF; resolve findings.
- [ ] Commit, publish PR and verify full CI.
- [ ] Learning → skill: assess findings; none yet.

## Decisions

Behavior-preserving extraction only. Keep authentication/private snapshots, partition staging, canonical hashing and publication in the callers. Callback output remains provisional. No provider requests or persistent-store changes. Complete local invocations within five minutes; CI runs the full suite.

## Evidence

First traversal test failed on the missing module, then passed through the new interface. Thirteen direct seam cases now pass; the initial two-caller group passed 59 cases. Broader qualification remains in progress.

Further local checks: 51 census/projection/architecture cases passed in 16.55s. Scoped Pyright: zero errors/warnings after narrowing the whole-archive count and explicit optional member-size accounting.
