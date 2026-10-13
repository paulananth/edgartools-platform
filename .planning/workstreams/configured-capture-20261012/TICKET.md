# Isolated configured capture and retirement integration

Status: local capture qualification complete; publication/CI in progress. Broader retirement incomplete. Starting main 692e0215; own branch/worktree
`codex/configured-capture-20261012`.

Operator agreed: keep Claude's active changed-data files, implement isolated
configured capture first, and integrate adapter/Company-manifest retirement
once shared changes land. No SEC request, source activation or deployment is
permitted by this implementation instruction.

## Parts

- [x] Inspect current callers, authority/recovery contracts, history and GoF seams; verify dedicated ownership against Claude's active paths. Verified history, production caller inventory and overlap guard, 2026-10-12 20:59 ET.
- [x] Define a frozen configured capture request/receipt with explicit limits, independent readback, authorization and immutable recovery evidence. Verified docs/design against 58 offline tests, 2026-10-12 20:59 ET.
- [x] Implement Python configured transport and registered provider.capture worker/verifier, using Rust configured completeness checks and no Bookkeeping domain callbacks. Verified 58 capture checks and 49 maintained control tests, 2026-10-12 20:59 ET.
- [x] Qualify conditional reuse, malformed/oversized/redirected responses, prior-receipt corruption and authority failures before network effects. Verified 58 capture checks and 49 maintained control tests, 2026-10-12 20:59 ET.
- [x] Prove real PG16 restricted worker/verifier lifecycle, journal-before-request, journal outage, completion lost acknowledgement and expired/taken-over leases offline. Verified 58 capture checks and 49 maintained control tests, 2026-10-12 20:59 ET.
- [x] Verify runtime pinning, installed path and unchanged control independence; qualify the supported source/configuration scope without claiming live provider proof. Verified: Installed committed-wheel capture/public verifier and no-duplicate-file checks passed; describe command and runtime digest test passed, 2026-10-12 21:17 ET.
- [x] Retire sec_client.py only after replacement and executable-caller/test inventory proves the old path is unnecessary. Verified: Production/script/package caller inventory is empty; retirement and transport-only architecture boundaries passed in 990 unit/architecture tests, 2026-10-12 21:17 ET.
- [x] Correct the stale Change Journal capture specification to match public renewal/Journal sequencing, preserving control-only ownership and explicit offline qualification. Verified: Standards reviewer confirmed the corrected renewal/Journal/renewal sequence and logical effect keys, 2026-10-12 21:17 ET.
- [x] Standards, Spec and GoF reviews resolved; native/frame coverage audit found no remaining significant in-scope behavioral gap after 6 added PG16 cases and 19 storage/frame tests, 2026-10-12 21:17 ET.
- [x] Align the Company acquisition reference and README discovery link with the qualified worker and pending integration; verify genuine page selection and unsupported approved format/bound refusal. Verified 6 real PG16 cases, guide/README readback and ownership/overlap guard, 2026-10-12 21:29 ET.
- [ ] Review Standards, Spec and GoF; resolve findings, guard/commit and publish a reviewable result with CI evidence.
- [ ] ~~Live SEC/continuation-page qualification and source activation~~ remains Issue 20 L8: requires explicit provider authorization and approval of exact source evidence/version; no requests in this slice.
- [ ] ~~Adapter mapping/fallback retirement (L7)~~ integrate after Claude's changed-data changes merge: store.py and installed-bundle tests are his active files.
- [ ] ~~Company manifest writer replacement~~ integrate after the changed-document selection interface lands; do not duplicate Claude's receipt-selection work.

Rust presence/member predicates and READING reference also changed; full Rust acceptance passed. Source integration, approval and activation behavior remain unchanged.

## Acceptance


Configured capture is a Python integration called through the existing external
worker protocol. Parsing/completeness computation uses the configured Rust core.
No worker receives a Bookkeeping engine/private method. Verify live work
permission and acknowledged journal intent immediately before each network
request; refuse redirects and bound bytes. Retry after a durable complete
capture must reuse its immutable response evidence rather than refetch, then
reconcile journal/control delivery. Every conditional 304 must read/hash-verify
its declared previous bytes. Verifier independently authenticates configuration,
request, immutable response and journal receipt. No standalone local mutable
control store or silent fallback. Source versions/URLs/timestamps/bounds and
captured semantics remain explicit. Fixtures never constitute live SEC proof.
