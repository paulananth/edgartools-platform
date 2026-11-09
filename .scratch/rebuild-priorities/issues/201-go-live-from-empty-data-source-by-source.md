# 201: Go live from empty data, source by source

Priority: 201. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 08:37 ET (operator: "We need a ticket to start everything from scratch for go-live with each source /wayfinder"; scope: "Just start empty for data not rules no proving").

Type: task, charted with wayfinder. Status: open. Blocked by: none.

## Destination

Every source has gone live from empty data stores. Rules stay, reference code sets (RDM) stay and captured files stay as they are. Only data is emptied: MDM masters and mastering records, Silver, Bookkeeping runs and the Change Journal. There is no proving step: no acceptance trace, no sample-then-full proof and no comparison run. Each source is loaded once through the real load, in the order of [the initial load sequence](../../../docs/initial-and-daily-source-load.md), and its counts are recorded.

## Out of scope

- Rules, RDM code sets and captured files (kept).
- Proving and comparison runs (operator: "no proving").
- New provider requests (the load uses captured files; each request needs the operator's word).
- Snowflake gold and any hosted environment.

## Sources, in load order

Each source: empty its data, load it from its captured files, record counts (files, records, masters, links waiting). One line ticked per source, with its ET stamp.

- [ ] SEC company (Companies, by CIK)
- [ ] N-PORT registrant (Companies, by CIK)
- [ ] Form ADV filings and custodians (adviser and custodian Companies)
- [ ] GLEIF Level 1 (finds Companies, never creates), then GLEIF relationships
- [ ] SEC submissions person (Persons)
- [ ] N-PORT fund (Fund Structures)
- [ ] OpenFIGI, then 13F securities and N-PORT security (Securities)
- [ ] SEC ownership (Form 4 relationships)
- [ ] 13F filings
- [ ] SEC company facts and SEC registration (Silver only)
- [ ] Reconcile waiting links once both endpoints exist; record the totals

## Prerequisites

From [the initial load sequence](../../../docs/initial-and-daily-source-load.md), steps 1 to 4. The doc's "what blocks the full load" table is older than the rebuild, so recheck each line before relying on it.

- [ ] Capture inventory frozen: every retained SEC, GLEIF and OpenFIGI delivery with files, receipts and hashes (no provider request).
- [ ] Rules documents loaded and RDM code sets restored with exact version pins (SEC place codes, place types, ownership transaction codes).
- [ ] Each source registered on the new store, with its targets, manifests and worker and verifier logins; the matching rules the operator approved are the ones switched on.
- [ ] Name counts built from whole populations: the full SEC submissions, the ticker catalog and the full GLEIF Level 1 publication.
- [ ] Sources with an incomplete path named, not omitted: N-PORT run builder (ticket 79), OpenFIGI listing enrichment (ticket 80), and complete mastering targets for ADV, ownership and 13F.
- [ ] Ticket 199's open parts that a fresh load meets: the rules version recorded on mastering records, and the Silver `links` stale-lease stop seen in the GLEIF loads.
- [ ] Ticket 02's origin check of the 327 governed-store runs done first, since an empty start erases that evidence.

## Init, decided

- Environment (operator, 2026-11-09 08:42 ET: "I recommend a new store. Call it local-staging"): a new store named `local-staging`, not the shared `local-test-server`. A new store leaves the current stores as they are, so no backup is needed first.
- Bookkeeping and the Change Journal start empty (operator, 2026-11-09: "Empty bookkeeping, empty change journal", "This is for ticket 201 init"). MDM and Silver data start empty too.
- [x] Initialize the store from the skills alone (2026-11-09 08:46 ET). First try failed on gaps in the skill (no interpreter in the command, a checkout behind `origin/main`, a store tied to its creating checkout, a stale skill link); `local-staging` was dropped, the skill text fixed in a working copy, and the retest passed in 17 s: six stores, Bookkeeping, Change Journal and Silver without rows, MDM with six setup tables holding rows. The skill fix waits on the overlap guard (another runtime edits `skills/data-operations/SKILL.md`).

## Open decisions, to settle one at a time

- [x] Environment: `local-staging`, a new store (see Init, decided). Backup of the current stores: not needed.
- [ ] Whether a source that cannot yet load (ticket 79 N-PORT run builder, ticket 80 OpenFIGI listing enrichment, ADV and 13F mastering targets) is deferred or loaded as far as its path supports. The load sequence says to report the missing source and stage, not to omit it.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
