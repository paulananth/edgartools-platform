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

## Open decisions, to settle one at a time

- [ ] Which environment is emptied: the shared `local-test-server` (needs every user's word, since shared data is never replaced while others use it) or a new store from `local-test-stores.py up`. Recommended: a new store, kept as the go-live store.
- [ ] Take a backup of the current stores before emptying, and name where it is kept.
- [ ] Whether a source that cannot yet load (ticket 79 N-PORT run builder, ticket 80 OpenFIGI listing enrichment, ADV and 13F mastering targets) is deferred or loaded as far as its path supports. The load sequence says to report the missing source and stage, not to omit it.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
