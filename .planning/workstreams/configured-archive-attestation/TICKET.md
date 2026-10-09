# Configured archive attestation caller retirement

## Checklist

- [x] Inspect current callers, source contracts, history and overlap ownership; executable search and overlap guard pass. 2026-10-09 09:20 ET
- [x] Add a generic bounded configured archive attestation boundary; preserve full-source hashes, ordinals, counts, EOF, private snapshot and callback exception identity. Six independent historical parity cases and non-GLEIF/fault tests pass (21 cases, 15.25s); existing affected tests 97 passed (48.93s). 2026-10-09 09:20 ET
- [x] Switch publication verification and Name Census callers; remove the old runtime inspector, preserving publication authority separately. Runtime/script search shows no retired inspector call; historical oracle is test-only. 2026-10-09 09:20 ET
- [ ] Verify all six GLEIF member/format contracts, independent historical parity and deliberate transport/EOF faults; prove a non-GLEIF configured source uses the same boundary.
- [ ] Run affected tests and PostgreSQL 16 acceptance without prerequisite skips; review, commit, push and full CI gate.

## Parent goal remains active

This caller cutover is part of complete old-parser retirement. Remaining work
includes configured record-evidence interpretation, complete Name Census
construction/cascade parity and installed full-population replay/recovery.
Self-contained skills, bundled Rules creation and parsing/MDM orchestration
need a final installed audit. No deployment or Rules activation is included.

## Design review

The GoF review examined JSON/XML cutovers #842/#843 and the active publication
and census consumers. Keep functional composition. Reuse the existing generic
stream policy and native engines; separate publication-authority validation
from archive transport. A class hierarchy adds no value here. The extraction
adds an interface whose fidelity must be proven with independent old-runtime
reports and callback/refusal tests.
