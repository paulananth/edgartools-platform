# 211: Finish the go-live: the remaining sources and the hosted store

Priority: 211. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 14:35 ET (operator closed ticket 201: "201 close the ticket"; its unfinished parts come here with their evidence, none dropped).

Type: task. Status: open. Blocked by: none.

## Destination

Every source is loaded on the hosted Snowflake store from the local captures (no AWS), with its counts recorded, and `local-staging` holds the same set. Read and combine run in the loader (ticket 210); only mastering and silver write the database.

## Checklist

- [x] (2026-11-11 14:35 ET) Hosted rules refreshed from `main` and active (15 versions): `rules load --root rules` then `rules activate` with `governance.env`.
- [ ] Hosted SEC company load (76,231 documents in 150 bundles, the target marked local): running since 13:32 ET, 64 of 150 bundles at 14:32 ET, no failure; about a minute a bundle.
- [ ] GLEIF Level 1 (finds Companies, never creates), then GLEIF relationships
- [ ] OpenFIGI, then 13F securities and N-PORT security (Securities)
- [ ] SEC ownership (Form 4 relationships)
- [ ] 13F filings
- [ ] SEC company facts and SEC registration (Silver only)
- [ ] Reconcile waiting links once both endpoints exist; record the totals
- [ ] Skill gaps from the rules step: `data-operations` step 2 says "`rules load` saves every file under a root; do not use it here" and step 3 omits `governance.env`, while the go-live path for a new store is `rules load` then `rules activate` with `governance.env` (as `data-onboarding` APPROVE.md says); make the skills agree.
- [ ] Ticket 199's open parts that a fresh load meets: the rules version recorded on mastering records, and the Silver `links` stale-lease stop seen in the GLEIF loads.
- [ ] Ticket 02's origin check of the 327 governed-store runs done first, since an empty start erases that evidence.
- [ ] Whether a source that cannot yet load (ticket 79 N-PORT run builder, ticket 80 OpenFIGI listing enrichment, ADV and 13F mastering targets) is deferred or loaded as far as its path supports. The load sequence says to report the missing source and stage, not to omit it.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
- [ ] Load each source into the hosted store from the local captures, no AWS (2026-11-11 06:02 ET; operator: "after init load each source in snowflake from local no aws"). Done so far on the hosted store: GLEIF subfund pairs (1 document), N-PORT registrants (1), 13F securities (52, 22 minutes), N-PORT funds (1, 12 minutes) and OpenFIGI tickers (4, 7 minutes). OpenFIGI answers (7,714 documents, 16 bundles) is running, 3 bundles at once with 1 worker each. Still to load: the finish of the N-PORT securities run, GLEIF Level 1 (needs its scope files), SEC company (needs its Name Count), ADV, ownership, 13F filings, company facts and registration.
- [ ] Hosted counts: ticket 209's count of records explained, and each source's stored and set-aside counts, on the hosted store once its loads finish.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
