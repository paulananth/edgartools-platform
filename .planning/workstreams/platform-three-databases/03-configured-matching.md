# Configure the remaining matching record choices

Part of item 1: complete the normal MDM caller on PostgreSQL and MySQL.
This part removes record-shape and eligibility choices from pair comparison;
it does not complete MySQL's normal MDM migration or commit path.

- [x] Rebase onto merged #1141 and inspect current ownership and matching history — live merge/ref checks, clean rebase onto 44e29eb9 and overlap guard; 2026-10-22 20:26 ET.
- [x] Declare name, identifier, census, eligibility and address selectors in the pinned engine catalog; preserve the existing approved comparison outcomes — 215 affected unit cases and 29 PostgreSQL caller/correction/#1141 cases passed; 2026-10-22 20:26 ET.
- [x] Pass that declaration through the normal Python facade to the shared Rust calculation, with no entity or source choices in those record selectors — freshly built native wheel; affected cases passed; 2026-10-22 20:26 ET.
- [x] Prove invented field names, namespace and kind through the normal comparison facade, including refused/missing/withheld values — 22 configured-comparison cases, including two coexisting profiles and registration refusal of unknown/incompatible profiles; 2026-10-22 20:26 ET.
- [x] Verify the affected matching, catalog and normal PostgreSQL caller cases, preserving #1141's effective-time behavior — 215 unit cases in 9.72 seconds and 29 PostgreSQL cases in 12.34 seconds; 2026-10-22 20:26 ET.
- [x] Qualify the catalog/native contract and worker recovery through the independently installed five-wheel bundle — committed 74c13c36 installed all five wheels without duplicate modules, the invented profile passed outside the checkout, and streamed-worker interruption/recovery passed; three cases in 236.03 seconds; 2026-10-22 20:31 ET.
- [x] Review Standards, Spec and GoF — resulting diff reviewed against the three axes below, current main and the declared bounded scope; `git diff --check` and overlap guard passed; 2026-10-22 20:31 ET.
- [x] Publish this bounded change for review — draft PR #1142 opened and its published head a012c428 read back from GitHub; 2026-10-22 20:33 ET.
- [ ] Verify published CI checks and mark the bounded PR ready; stop monitoring on terminal failure/closure or a 20-minute deadline.
- [x] Learning → skill: none; existing configuration, frozen execution identity, package qualification and comparison/storage separation guidance applies; 2026-10-22 20:31 ET.

## Design evidence

`record_pairs.rs` changed in #1121 and #1141, while `matching.py` and the
catalog already supply configured reference tables. Pair comparison still
selects a particular kind, identifier namespace, census keys, name/status
fields and address preference directly in Rust. A new record layout therefore
requires engine edits even when the comparison algorithm is unchanged.

Extend the existing catalog-to-native command boundary with one validated
record-shape declaration. Keep the current facade and calculation; no new
strategy classes, registry or parallel algorithm. The cost is one explicit
native command contract and corresponding package rebuild. Source-specific
candidate retrieval and its indexes remain a separate unfinished part of
the parent checklist.

## Scope and review

Standards: own dedicated worktree, additive configuration, historical migrations
unchanged, overlap guard clean. Tests use private worktree-specific testmon
caches and disposable databases. The optional local pgserver backend was
unavailable; the existing Docker test fixture then passed and stopped its own
server. No retained store, provider request, activation or cutover changed.

Spec: comparison record choices now come from named catalog profiles. Existing
rules retain the compatibility profile; another rule can explicitly select a
different profile, which registration checks against its kind. The catalog is
already part of execution identity. Name/status comparisons honor declared
withheld fields. This proves comparison configuration, not arbitrary candidate
retrieval or a supported normal MySQL Store. Those parent parts remain open.

GoF: retained the current facade and native algorithm. A typed command field
carries the selected declaration; no new class hierarchy or second algorithm.
The extra configuration is justified by the existing fixed record choices and
the demonstrated invented vocabulary. Its cost is explicit schema validation
and installing the matching catalog and native wheel together.
