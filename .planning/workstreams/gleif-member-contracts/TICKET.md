# GLEIF member contracts and complete parser retirement

Continue the original full self-sustaining skills / Rules creator / parsing / MDM / custom orchestration goal. PRs #833 and #834 are merged. Codex owns this branch and worktree. Local qualification only; preserve the active runtime until complete replacement evidence exists.

- [ ] Bundle configured contracts for Level 1, relationships and reporting exceptions, both JSON and XML, approved scope and authenticated publication metadata.
- [ ] Qualify complete captured member bytes, counts, canonical hashes, ZIP CRC and EOF; compare selected configured outputs against historical results.
- [ ] Qualify installed XML publication refusal and recovery with restricted PostgreSQL 16.
- [ ] Replace active GLEIF runtime consumers and remove legacy parsing imports and implementations after complete equivalence.
- [ ] Replace remaining Company landing/preparation/provenance/census/cascade routes with configured reading and mastering.
- [ ] Prove installed empty-store 6,414 Company / 3,052 CIK+LEI population, unchanged replay and recovery.
- [ ] Reconcile Claude/Codex trackers and retire remaining parser/adapter/fixture/capture code according to parent issue 20 L3-L8.
- [ ] Independent review, affected tests, full CI and reviewable PRs.
- [x] Compare complete cached relationships and reporting-exceptions JSON against independent ijson decoding; verified 487,721 / 6,351,397 records, exact types/key order, canonical hashes, ZIP CRC and EOF in stored full reports (2026-10-06 20:50 ET).
- [x] Download matching 20260911-1600 XML archives after operator approval; verify all three publisher compressed sizes and store SHA-256 capture receipts and exact publisher API metadata (2026-10-06 20:51 ET).
- [x] Correct captured JSON wrapper names and independently fix fixtures; affected member/header/archive fault tests passed 53 cases in 2.18s (2026-10-06 20:55 ET).
- [ ] Qualify full downloaded XML with separately pinned capture ContentDate; first attempts correctly refused because API publication slot differs from all three member ContentDates.
- [ ] Add generic direct header/context count equality so a malformed creator contract cannot pin inconsistent counts; independent review reproduced header4/context3/actual3 acceptance.

Verified foundation: full Level 1 JSON framing and configured selected-output comparison are recorded in the prior GLEIF workstream; merged #834 supplies XML framing through the native interpreter and private worker boundary. The full CI gate 37551604093 passed on 22c7e922. This is not complete GLEIF XML corpus or mastering qualification.

Capture inventory: three pinned GLEIF JSON ZIP members exist in the local research cache; no captured XML ZIP was found there. Authorized S3 inventory found only the prod bronze bucket and no obvious GLEIF prefix among the inspected roots. Further capture evidence is needed; these limited prefix listings are not a proof that no XML exists anywhere.

The operator subsequently approved direct GLEIF XML downloads. Archives and sidecars are at `/private/tmp/codex-gleif-xml-20261006`; publisher metadata and download receipts are recorded here. Publication slot is 16:00, while actual XML ContentDates are Level 1 16:07:44Z, relationships 17:12:30Z, exceptions 16:56:35Z. These observed capture dates must not be presented as API-supplied dates. XML qualification compares canonical typed map values (configured maps sort keys), preserving list/source order; it does not claim source XML key-order parity. Current framing proof is not installed full mastering or runtime retirement.

- [x] Install c36199c7 bundle and execute all six GLEIF templates outside checkout, with independent worker verification; one installed test passed, 25 deselected, no skips in 111.71s (2026-10-06 20:58 ET).

- [x] Regress API-slot/content-date confusion and mid-scan implementation change; affected tests passed 57 cases in 3.30s (2026-10-06 20:59 ET).
- [x] Push reviewable contracts/qualification change and create non-draft PR #841; live GitHub head c36199c7, CI 37554733174 running (2026-10-06 20:58 ET).
