# Configured archive attestation caller retirement

## Checklist

- [x] Inspect current callers, source contracts, history and overlap ownership; executable search and overlap guard pass. 2026-10-09 09:20 ET
- [x] Add a generic bounded configured archive attestation boundary; preserve full-source hashes, ordinals, counts, EOF, private snapshot and callback exception identity. Six independent historical parity cases and non-GLEIF/fault tests pass (21 cases, 15.25s); existing affected tests 97 passed (48.93s). 2026-10-09 09:20 ET
- [x] Switch publication verification and Name Census callers; remove the old runtime inspector, preserving publication authority separately. Runtime/script search shows no retired inspector call; historical oracle is test-only. 2026-10-09 09:20 ET
- [x] Rebase onto origin/main 702a750a. Keep `stream_policy` as the caller name, keep the installed script's newline escape, and state the attestation wording without a source name. 178 affected tests passed in 10.51s: genericity, attestation, XML header bounds, census names, and the GLEIF source cases. 2026-10-09 10:55 ET
- [x] Verify all six GLEIF member/format contracts, independent historical parity and deliberate transport/EOF faults; prove a non-GLEIF configured source uses the same boundary. `tests/engine/test_source_attestation.py`: 21 passed in 2.59s on 2026-10-09 15:06 ET. The six contracts are level1, relationships, and reporting-exceptions, each in json and xml. The engine build is commit ae627570.
- [x] Run the affected attestation tests: genericity, attestation, XML stream, GLEIF reading contracts, census names, and GLEIF source cases. 209 passed in 10.98s on 2026-10-09 15:39 ET, with the engine build from commit ae627570.
- [ ] Run PostgreSQL 16 acceptance without prerequisite skips; review, commit, push and full CI gate.

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
