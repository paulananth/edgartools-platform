# Shared configured source traversal

Design only. Based on main `c997b860`; scope confirmed by the operator: preserve existing behavior while sharing traversal implementation.

## Outcome

Source Extract production and full-source attestation use one deep Python module for common configured traversal. They retain their different publication duties. This is an extraction of existing orchestration around the existing native engine adapter, not a change to parsing, source mappings or approval rules.

## Module and seam

Proposed implementation location: `edgar_warehouse/workers/source_traversal.py`.

The module owns compilation of the existing stream declaration, bounded context/ordinal validation, common archive opening/validation, native scanner selection and complete-EOF accounting. Compile once for repeated input traversal. Its interface must not expose native engines for callers to dispatch themselves.

The caller supplies an authenticated private snapshot, its context and lookup values, a record callback and the explicit archive policy appropriate to that caller. A successful return supplies the existing record count and expanded-byte evidence. Callback output remains provisional until successful completion; the module has no artifact writer, database connection or publication authority.

Keep ordinary functions and a small internal representation. No plugin registry or class hierarchy. Final function names and representation are implementation choices.

## Caller duties

### Source Extract production

- `source_read` authenticates receipts, input-bound context and lookup evidence through existing code.
- `source_stream` retains private partition sizing, row/spool/index accounting and output receipts.
- Preserve configured ZIP member selection and all existing JSON, XML and delimited behavior.
- Every input must finish successfully before any externally visible partition or index write. Completing one input grants no publication authority for a multi-input task.
- Independent verification reconstructs the same output through the same traversal seam.

### Full-source attestation

- `source_attestation` retains compressed-byte/hash authentication and its private snapshot.
- Retain its stricter requirement for exactly one unencrypted ZIP member. Do not let extraction's member-selection option weaken this rule.
- Retain full-record selection, ordinal checks, canonical content hashing, pinned expected count and empty lookup-set policy.
- Retain supported JSON/XML attestation behavior; this refactor adds no attestation format support.
- A report is returned only after complete valid EOF. Preserve callback exception identity, including cancellation.

## Compatibility

- Preserve output bytes, source identities, ordering, ordinals, contract immutability, reports, refusals and resource bounds. Preserve native error codes and externally relied-on exception behavior.
- Keep source-contract Rust code and SourceEngine's existing eager/stream distinction intact.
- Cover the new module in every affected runtime fingerprint. In-flight runs finish with their pinned runtime; changed code is never relabeled with an old digest.
- ADR 0016's independent MDM and analytical mappings and existing destination enforcement remain unchanged.
- Source Extract evidence/Name Frequency is candidate 2 and is outside this design.

## Proof through the interface

Use invented local fixtures; no provider access or persistent-store changes.

- [ ] Establish affected existing test baseline with testmon; keep every local invocation below five minutes.
- [ ] Test traversal through its interface for named/bare JSON arrays, XML with headers, delimited data, plain inputs and permitted ZIP inputs.
- [ ] Prove extraction may select its configured member while attestation still refuses extra members.
- [ ] Prove empty input/context checks, count mismatches, malformed/truncated/trailing content, CRC faults, forged expanded length and resource-bound failures.
- [ ] Prove callback failure/cancellation identity and unchanged input contracts.
- [ ] Retain worker/verifier replay, receipts, lookup authentication and multi-input no-publication-after-later-failure tests.
- [ ] Retain all six GLEIF member/format attestation reports and canonical hashes.
- [ ] Prove edits to the traversal module alter affected runtime fingerprints.
- [ ] Review Standards, Spec and GoF after implementation; run full CI.
- [ ] Learning → skill: assess implementation findings; none yet from this design-only review.

Existing suites include `tests/engine/test_source_stream_worker.py`, `test_xml_stream_worker.py`, `test_source_attestation.py`, `test_source_lookup_receipts.py`, `test_partitioned_reading_consumers.py` and `test_check_confirms.py`.

## Deletion test

Both callers lose their duplicated archive/scanner dispatch and EOF reconciliation. Attestation stops importing its compiler from the extraction/output module. Partition publication and canonical content hashing stay visible in their respective callers. If the change merely adds forwarding while both traversal copies remain, it has failed.

## Review status

**Standards:** read-only review from a dedicated worktree; no repository or shared-store mutation. Implementation requires a fresh branch and worktree.

**Spec:** the operator selected candidate 1 and agreed to preserve each caller's rules. Detailed interface design is recorded here for confirmation; no code has been changed or behavior qualified.

**GoF:** repeated traversal is evidenced by generic attestation `13942dcf`, delimited/member-selection `69fb3ee3` and bare-array `24de5935`. Plain extraction is sufficient. Cost: another module to navigate and moderate recovery/compatibility risk; benefit: one implementation for two callers. No speed claim.

Recorded 2026-10-17 15:12 ET.
