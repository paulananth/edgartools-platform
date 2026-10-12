# Independent review

Baseline: starting main `7f1e8856`; reviewed implementation `af100aa7` rebased
onto `9bed91fd`, plus final byte-return refinement. Standards, Spec and GoF
ran as independent read-only agents; no reviewer changed implementation files.

## Standards

No concrete correctness, security or compatibility defect. Initial P2 evidence
finding: raw measurement hashes preceded the final formatter, migration and
facade edits, and acceptable placement cost lacked explicit thresholds.
Resolved by fresh separate-mode qualification with current hashes and fixed
wall/transfer/memory/SQL-call acceptance. Root independently verifies every
runtime SHA against both final evidence files. Final byte binding/adapters were
rechecked: same Rust serializer, SHA over returned bytes before JSON decoding,
unchanged legacy behavior and runtime pinning. No code findings remain.

## Spec

Initial P2 findings: journal timing used a file sink and memory combined both
engines. Resolved with pinned baseline/native JournalPublisher, actual
restricted ChangeJournal append/read-back, separate mode subprocesses and
PostgreSQL servers, sampled client/server RSS, and explicit shared-mapping
limitations. A further P2 baseline-method finding identified an extra SQL hash
in old_verify absent from the public baseline worker. Corrected to its exact
payload retrieval; no artificial baseline verification cost remains. Refreshed
200/600 evidence passes unchanged thresholds. No runtime defect found in the
byte-return refinement. Remaining database candidates are honestly retained or
conditional, not falsely reported retired.

## GoF

No actionable findings. Keep the payload adapter, existing Python facade and
native serializer; history shows representation/delivery changes rather than
a growing provider/algorithm axis. The byte-return helper addresses measured
memory without another hierarchy or serialization rule. Old/new lease claim
bodies duplicate a small authority transition; inspected history does not show
policy drift, and sharing it would replace frozen-client behavior and require
additional compatibility qualification. Retain this deliberate compatibility
cost, with mixed-client fence/concurrency tests.

## Documentation audit

Release audit required existing-store migration instructions, refreshed map
status, and accurate completed/no-work retry terminology. All are corrected;
lost-ack recovery is separately fault-injected in the public worker test.
Portable instructions stay self-contained. Reading/combining grammar and
onboarding/approval/activation instructions remain unchanged. Final CI/merge
and final-head installed proof are recorded separately in TICKET/RESULTS.
