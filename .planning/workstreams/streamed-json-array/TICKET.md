# Bounded native JSON array streaming

Continue the complete self-sustaining Rules creator, parsing/MDM/custom orchestration and old-parser retirement goal. Parent PR #828; local qualification only.

- [x] Inspect active GLEIF/archive consumers, bounded native grammar and change history; apply GoF review — 2026-10-05 09:10 ET, consumer/history inspection and both independent review axes.
- [x] Implement generic native single-wrapper JSON-array streaming with duplicate-key, object-record, finite-number, depth, byte, record and EOF checks; bounded callbacks only prepare candidate data — 2026-10-05 09:10 ET, 94 native tests and 331 non-installed engine tests pass.
- [x] Expose the native reader through the existing Python parser boundary and qualify exact typed output/refusal decisions against the historical GLEIF JSON reader — 2026-10-05 09:10 ET, finite-parity.json records 2,065 cases, zero differences; no universal or full-archive claim.
- [x] Add authenticated private artifact snapshots with bounded memory/disk and explicit lifecycle — 2026-10-05 09:10 ET, nine unit cases pass; both independent reviews found no scoped issue.
- [ ] Wire configured streaming and replace active JSON parsing only after installed/runtime dependencies and complete source evidence qualify; preserve XML completion scope.
- [ ] Verify native and Python tests, installed restricted PostgreSQL 16 path, independent reviews and complete CI; commit/push/create PR.
- [ ] Finish XML streaming, active MDM preparation/provenance/census/cascade, full installed population/replay/recovery and remaining old-parser deletion in the parent goal.

GoF: GLEIF archive, record evidence and native source engine history show changing source policies but stable parser function interfaces. Retain functions and serde visitors; a source-specific class hierarchy would add cost without removing the measured whole-document memory limitation. No SEC requests, Rules activation or cloud deployment.

## Measured findings

Default serde floating-point decoding changed 608 of 1,998 deterministic finite float values. Enabled `float_roundtrip`; the complete 2,065-case typed/refusal audit now has zero differences. A deliberate one-ULP fault is detected. Full native regression: 94 pass. Python engine regression excluding the installed-bundle file: 331 pass in 36.44 seconds. Artifact lifecycle tests: nine pass in 0.37 seconds.

The historical decoder refuses -9223372036854775808; the native core supports it. The explicit `min_integer` boundary preserves historical refusal when requested. Raw record buffering allows `max_record + 65,536` bytes; the separate encoded-record cap remains strict. Whitespace acceptance and oversized refusal are tested. These are explicit policies, not universal equivalence evidence.

Independent Standards and Spec reviews closed the raw-buffering clarification and authenticated snapshot lifecycle findings. Active source.read is still eager, active GLEIF JSON/XML parsers remain, and no source rules were activated. The installed streaming-boundary trial is added but requires the committed bundle before it can run.
