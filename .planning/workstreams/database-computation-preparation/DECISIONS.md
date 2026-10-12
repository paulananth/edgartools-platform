# Database placement decisions

Evidence base: main `7f1e8856`, plus this branch's checksummed migration 016.
This is qualification of the active publication path and assessment of the
other SQL candidates, not a claim that every SQL expression has been removed.

## Implemented extraction

Active `Store.deliver_one`, `JournalPublisher` and `mdm.publish.verify` read
`mdm.outbox_input` by batch/consumer. Rust shapes the envelope from raw JSONB
text; Python coordinates, hashes, decodes for the publisher and verifies.
Raw numeric scale/precision survives until the committed hash comparison.
Legacy populated payloads retain their exact text. No new copy is stored.

The new four-argument `claim_outbox_input` takes an optional batch restriction
and locks the earliest undelivered generation before checking that restriction.
It shares the original outbox row, fence, lease and history; it introduces no
second control store. Existing claim and delivery-view APIs remain available to
already frozen runtimes. New worker runtime identity pins the adapter, facade
and native binary. Old migration files/checksums are unchanged.

`canonical_inputs=True` is restricted to authenticated database JSONB text:
Rust validates one JSON value per part and reuses its bytes; the caller must
compare the final SHA-256 with the committed expected hash before publication.
The general formatter separately qualifies PostgreSQL numeric/string semantics.
Neither mode establishes an RSS cap. General normalization has a 64 MiB byte
budget. Publication derives its output budget from authenticated stored parts:
JSONB numeric exponent expansion can exceed the compact request size, so an
arbitrary new fixed ceiling would reject previously accepted intent. It does
not increase MDM request limits or generate amplified numeric output.

## Computation inventory and disposition

| Existing work | Decision and evidence | What remains / prerequisites |
|---|---|---|
| Outbox delivery envelope construction and read-side hash verification, migration 014 | **Moved on the active path:** Rust generic object preparation; Python callers. `test_program_publication_inputs`, retained pre-014/014 tests, public worker and installed bundle prove hashes, recovery and compatibility. | Commit derives the expected hash independently in SQL, inside atomic batch/checkpoint/outbox persistence. This is destination integrity enforcement. Removing it would make worker-produced hashes authoritative. Compatibility SQL remains for frozen consumers. |
| Journal envelope canonicalization/hashing, journal migration 001 | **Already prepared in programs:** `ChangeJournal.append` builds compact canonical text/hash in Python before calling `journal.append`. No database preparation round trip exists to remove. | SQL checks canonical content/hash, producer-key uniqueness and immutability. The standalone journal's minimal installed package stays independent of the Rust data engine. Its identifiers-only envelope and exact numeric version are a distinct protocol from JSONB text. |
| Batch/request structure checks; proposal effects-hash normalization, migrations 001/013 | **Retained authoritative checks:** Python prepares request/effects; SQL validates every writer, bounds, approved source/mapping, assessed effects and fresh dependencies. | The database's effects hash is the trust anchor for later save. Do not replace it with a trusted client hash. Request/assessment identities and old proposal replay stay unchanged. |
| Company scalar extraction and alias/version writes, migration 015 | **Retained indexed storage maintenance and consistency:** fields are already selected/materialized by programs. SQL stores the corresponding searchable columns alongside the canonical body in the same version transition. `test_clean_company_one_place`, per-kind view and MDM tests check one-copy fields, aliases and microsecond history. | Moving scalar preparation alone still needs independent body/column consistency enforcement, plus extra request metadata or a changed column protocol. No supplied scalars are trusted. A column-protocol redesign requires measured write/wire/read evidence and exact typed parity. |
| `entity_name`, `relationship_holds`, relationship/context shaping and chain traversal, migrations 006–010 | **Retained indexed retrieval consumers:** the name function is used by search indexes; temporal predicates and traversal select matching stored links under one database snapshot. Existing context and lookup tests exercise names, temporal boundaries, cycles, hop limits and indexed access. | These are not a permanent CPU exemption. A later caller redesign must retrieve the complete bounded closure and preserve snapshot consistency without whole-table exports; compare full transfer/round trips with current index probes. No new context API is introduced in this task. |
| Latest Stage folding/profile keys, migration 001 | **Conditionally movable current-state transition:** fold consumes the locked current Stage snapshot and ordered reading, not solely the incoming payload. `test_clean_stage_record` and binding tests pin clear/unknown/profile/revision semantics and delivery-order behavior. | A program-side port needs a bounded snapshot/CAS protocol and exact prior-row/revision checks in the commit. The separate history-fold port must not silently substitute history replay: late older readings deliberately leave the latest Stage row unchanged. |
| Stored-key joins, dependency freshness, approvals, uniqueness, leases/fences, history and atomic commits | **Retained database authority:** indexed lookup and restricted-role/concurrency/recovery tests continue to run. | Programs orchestrate bounded closure and retries; the database enforces live state and commits. |
| Snowflake row-local formulas and historical windows/rankings | **Still conditionally movable analytics work:** the current AWS native-pull/dbt consumer path is unchanged. Code inspection is not Snowflake replacement qualification. | Moving this serving path requires decimal/NULL/restatement parity and complete affected history, transfer/publication/refresh measurements. It is a separate analytics consumer migration, not delivered by the PostgreSQL publication qualification. |

## Design review

`gof-refactor-reviewer` inspected Store, publication/journal adapters, facade,
SQL definitions and history (`4ace81d3`, `9a72285b`, `c16968be`). Keep the
existing function/facade seams: no growing variation axis justifies Strategy,
Bridge or a new class hierarchy. A single pure preparation adapter makes the
SQL/native protocol boundary testable. The cost is maintaining frozen-client
compatibility and measuring text transfer/native conversion; qualification
records those costs instead of inferring a speedup from implementation language.
