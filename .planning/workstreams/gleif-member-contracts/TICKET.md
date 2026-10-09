# GLEIF member contracts and complete parser retirement

Continue the original full self-sustaining skills / Rules creator / parsing / MDM / custom orchestration goal. PRs #833, #834 and #841 are merged. Codex continues from merged main e6b541b3 on `codex/gleif-runtime-retirement-20261006` in the same protected worktree. Local qualification only; preserve the active runtime until complete replacement evidence exists.

- [x] Bundle configured contracts for Level 1, relationships and reporting exceptions, both JSON and XML, approved scope and authenticated publication metadata; #841 `e6b541b373d114a6a10a3bc8dd84151cf26c0d38` and #843 `f8f7876ee8c5e39baae74313d8a9182ecc42cb49` ship six templates, context-bound count/header metadata and the installed six-template execution/verification test. Creator fills explicit approved-scope rows; this is not source activation (2026-10-08 06:43 ET).
- [ ] Qualify complete captured member bytes, counts, canonical hashes, ZIP CRC and EOF; compare selected configured outputs against historical results.
- [x] Qualify installed XML publication refusal and recovery with restricted PostgreSQL 16; e4ca3ea8 installed trial passed, 26 deselected, no skips, 179.19s: bad header wrote no artifacts/master rows; restored same input retried the same run on attempt 2 through independent verification and mastering (2026-10-06 21:18 ET).
- [ ] Replace active GLEIF runtime consumers and remove legacy parsing imports and implementations after complete equivalence.
- [ ] Replace remaining Company landing/preparation/provenance/census/cascade routes with configured reading and mastering.
- [ ] Prove installed empty-store 6,414 Company / 3,052 CIK+LEI population, unchanged replay and recovery.
- [ ] Reconcile Claude/Codex trackers and retire remaining parser/adapter/fixture/capture code according to parent issue 20 L3-L8.
- [ ] Independent review, affected tests, full CI and reviewable PRs.
- [x] Merge PR #841 on the operator's explicit request; installed recovery and full CI 37556203441 passed on exact head e4ca3ea8, GitHub confirms merge e6b541b373d114a6a10a3bc8dd84151cf26c0d38 (2026-10-06 21:21 ET).
- [x] Compare complete cached relationships and reporting-exceptions JSON against independent ijson decoding; verified 487,721 / 6,351,397 records, exact types/key order, canonical hashes, ZIP CRC and EOF in stored full reports (2026-10-06 20:50 ET).
- [x] Download matching 20260911-1600 XML archives after operator approval; verify all three publisher compressed sizes and store SHA-256 capture receipts and exact publisher API metadata (2026-10-06 20:51 ET).
- [x] Correct captured JSON wrapper names and independently fix fixtures; affected member/header/archive fault tests passed 53 cases in 2.18s (2026-10-06 20:55 ET).
- [ ] Qualify full downloaded XML with separately pinned capture ContentDate; first attempts correctly refused because API publication slot differs from all three member ContentDates.
- [x] Add generic direct header/context count equality so a malformed creator contract cannot pin inconsistent counts; independent review reproduced header4/context3/actual3 acceptance. `tests/engine/test_gleif_header_count_equality.py`: 9 passed in 3.04s on 2026-10-09 15:59 ET. A header count of 4 with an input count of 3 is refused for level1, relationships, and reporting-exceptions, and no reading file is written.
- [x] Qualify installed count-bound XML refusal and same-run missing-artifact recovery through restricted PG16 Rules/Bookkeeping/MDM, with zero master writes on failure and complete verified retry; installed e4ca3ea8 trial passed in 179.19s, no skips (2026-10-06 21:18 ET).
- [x] Qualify full relationships XML: 487,721 records, 961,511,828 expanded bytes, exact scalar/list/canonical projection parity, metadata/count/CRC/EOF, 648.57s; stored full report (2026-10-06 21:06 ET).
- [x] Implement generic typed `equal` and regress mismatched header/reference/context counts for all three members; 116 native tests, 63 focused cases and 441 engine cases pass on isolated native build (2026-10-06 21:10 ET).
- [x] Wire direct count equality into the bundled XML templates after the pinned full corpus jobs finish; their template hashes must remain stable during scans. The shipped level1, relationships, and reporting-exceptions XML templates each refuse a header count that differs from the input-bound publication count. Same test file, 9 passed in 3.04s on 2026-10-09 15:59 ET.
- [ ] Hash the actual native extension before/after future qualification runs; current helper hashes package initializer only. Supplemental installed extension integrity matches original RECORD but supplies no retroactive pre-scan binary check.
- [x] Independent Spec/Standards/GoF review of typed equality and installed recovery: no remaining scoped blocker; full CI including five suites and aggregate gate passed in run 37556203441, then PR #841 merged (2026-10-06 21:21 ET). Full runtime retirement remains unchecked above.

Verified foundation: full Level 1 JSON framing and configured selected-output comparison are recorded in the prior GLEIF workstream; merged #834 supplies XML framing through the native interpreter and private worker boundary. The full CI gate 37551604093 passed on 22c7e922. This is not complete GLEIF XML corpus or mastering qualification.

Capture inventory: three pinned GLEIF JSON ZIP members exist in the local research cache; no captured XML ZIP was found there. Authorized S3 inventory found only the prod bronze bucket and no obvious GLEIF prefix among the inspected roots. Further capture evidence is needed; these limited prefix listings are not a proof that no XML exists anywhere.

The operator subsequently approved direct GLEIF XML downloads. Archives and sidecars are at `/private/tmp/codex-gleif-xml-20261006`; publisher metadata and download receipts are recorded here. Publication slot is 16:00, while actual XML ContentDates are Level 1 16:07:44Z, relationships 17:12:30Z, exceptions 16:56:35Z. These observed capture dates must not be presented as API-supplied dates. XML qualification compares canonical typed map values (configured maps sort keys), preserving list/source order; it does not claim source XML key-order parity. Current framing proof is not installed full mastering or runtime retirement.

- [x] Install c36199c7 bundle and execute all six GLEIF templates outside checkout, with independent worker verification; one installed test passed, 25 deselected, no skips in 111.71s (2026-10-06 20:58 ET).

- [x] Regress API-slot/content-date confusion and mid-scan implementation change; affected tests passed 57 cases in 3.30s (2026-10-06 20:59 ET).
- [x] Push reviewable contracts/qualification change and create non-draft PR #841; live GitHub head c36199c7, CI 37554733174 running (2026-10-06 20:58 ET).

- [x] Qualify full reporting-exceptions XML: 6,351,397 records, 1,933,382,825 expanded bytes, zero typed value differences, canonical hash/count/CRC/EOF, 1579.60s (26m20s); saved full report (2026-10-06 21:22 ET).

- [x] Wire direct count equality into relationships and reporting-exceptions XML templates; 54 affected tests pass in 2.51s, independent Spec/Standards review passes, and deliberate assertion removal makes shipped-template regression fail (2026-10-06 21:26 ET). Level 1 and native qualification hashing remain pending while scan 2655 is live.

- [x] Push count-equality continuation and create PR #842 at cffaf679; all five suites and aggregate gate passed in CI 37557207219 (2026-10-06 21:32 ET). Subsequent runtime changes require a new full gate.
- [x] Replace production GLEIF JSON parsing with member-configured native reading, retaining full-source canonical/domain digests and zero-based callbacks; 596 MDM/framing tests passed in 17.93s, including empty members, all-member exact reports, larger authorized record limits and original callback exception identities (2026-10-06 21:36 ET).
- [x] Retain historical JSON parser only as an independent qualification oracle outside production; executable runtime search finds no `_json_records` or `ijson` in gleif_source; audit tests import frozen oracle (2026-10-06 21:36 ET).
- [x] Require native binding in MDM extras and update lockfile; dependency image sync excludes the crate and keeps prebuilt-wheel installation; isolated actual manifest/lock/README context without crates passed exact dependency-sync dry run (2026-10-06 21:36 ET). This is dependency-plan proof, not a complete Docker image build.
- [ ] Verify complete configured JSON runtime reports against all three independent authenticated full-corpus hashes, with actual native-extension and source files pinned before/after; initial trial stopped deliberately after review found an exception-identity gap, no completion receipt claimed.
- [ ] Independent final runtime review, commit/push and full CI on the replacement head.

- [x] Qualify complete configured relationships JSON runtime: 487,721 records, 1,120,235,207 expanded bytes and canonical hash equal to independent full corpus proof; 158.97s, exact callback ordinals, raw/publisher count/size/CRC/EOF and actual native-extension/runtime hashes unchanged before/after; stored full report (2026-10-06 21:40 ET).
- [x] Reconcile issue 21 and initial completion audit with live merged #806/#807 checks and current read contracts; preserve unfinished retirement and 6,414/3,052 installed-population gates (2026-10-06 21:40 ET).

- [x] Merge PR #842 on the operator's request; exact ad1de482 head passed every CI check in 37558509346, GitHub confirms squash 17c21ef77c3522eb8361d9b6e0daee02590c2edc (2026-10-07 06:22 ET).
- [x] Preserve XML follow-up on dedicated codex/gleif-xml-runtime-retirement-20261007 branch; 626 affected tests passed in 17.91s (2026-10-07 06:22 ET).
- [x] Qualify full Level 1 XML framing: 3,428,477 records, 11,826,399,913 expanded bytes, zero typed differences, count/hash/CRC/EOF; 4539.76s (75m40s), stored report (2026-10-07 06:22 ET).
- [x] Qualify complete reporting-exceptions configured JSON runtime: 6,351,397 records, canonical hash matches independent corpus; 433.04s (7m13s), stored report (2026-10-07 06:22 ET).
- [x] Separate generic XML normalized header and record bounds, preserve strict record/raw caps, regress small-record compatibility and fail-closed worker publication; 117 native tests, 620 MDM/XML/archive tests, 58 member/stream tests pass on isolated new native wheel; independent Spec/Standards review finds no scoped blocker (2026-10-07 06:30 ET).
- [x] Complete Level 1 configured JSON runtime after the historical OSError 28 failure; successor completion is recorded in `.planning/workstreams/company-census-evidence/TICKET.md:18` and its `gleif-runtime/SUMMARY.json`: Level 1 3,428,477, relationships 487,721, reporting exceptions 6,351,397 in each of JSON and XML. No failed run retried for this reconciliation (2026-10-08 06:43 ET).
- [ ] Qualify replacement XML runtime against all three complete captured corpora with actual native binary pinned before and after execution.

- [x] Add reproducible full-runtime qualification CLI with pinned publisher/independent reports and actual native binary before/after; 10 JSON/XML valid and deliberate fault cases pass (2026-10-07 06:30 ET).
- [x] Install XML replacement f380eacd outside checkout and verify refusal/recovery on fresh restricted PostgreSQL 16; one trial passed, 26 deselected, no skips in 172.98s; installed direct_url.json confirms the exact commit (2026-10-07 06:46 ET).
- [ ] Rebase follow-up onto merged main, commit/push, independent final review and full CI on exact head.

- [x] Include contract-loading, canonical-encoding and metadata-normalization helper files in qualification hashes; 10 qualification good/fault cases pass with explicit helper evidence checks. The first replacement trial was deliberately interrupted after review found the omission; no complete report claimed (2026-10-07 06:31 ET).

- [x] Full replacement CI 37608031153 passed on ce7d90ec: 565 unit, 258 architecture, 571 MDM, 279 integration plus one expected failure, 495 engine and 117 native tests; all suites and aggregate gate pass, no prerequisite skips (2026-10-07 06:46 ET). Corpus scans remain unfinished.
- [x] Save and authenticate completed source-runtime corpus reports, superseding the historical session 30251 progress note; `.planning/workstreams/company-census-evidence/TICKET.md:18` and its `gleif-runtime/SUMMARY.json` record Level 1 3,428,477, relationships 487,721, reporting exceptions 6,351,397 in each of JSON and XML, frozen revision 3d3a7cb2 and native/runtime pins. This verifies saved terminal evidence, not a restarted scan (2026-10-08 06:43 ET).
- [ ] Finish Company continuation #844 census/classification/provenance and full installed population/replay/recovery; separate blueprint composition proof does not close these original requirements.

- [x] Reconcile current Person fixture state instead of repeating stale retirement claims: merged #816 removed its field conversion, and 19 raw-submissions/cohort tests preserve the full assertion/provenance digest (2026-10-07 06:48 ET). Adapter normalization and full captured-corpus mastering qualification remain pending.
