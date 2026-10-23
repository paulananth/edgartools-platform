# 05: A Person's Form 4 holdings land in silver

Priority: 25, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/05-a-person-holds-and-does-not-issue.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**Re-scoped (operator, 2026-10-22: "Agreed Remove HOLDS from MDM's relationship types", "Re-scope ticket 25 to land Form 4 holdings in silver"):** a holding is a position restated every filing with its amount, so it is a silver row carrying the MDM ids of the holder and the Security, never a relationship MDM masters. `HOLDS` is no longer an MDM relationship type (relationship-types-v6). The Person is never the issuer: `ISSUED_BY` still points at the Company or the Fund Company.

**What to build:** a silver table of Forms 3/4/5 holdings: one row per holding line (non-derivative and derivative, transaction and holding tables), as filed, with:
- **its as-of date**: the date the position holds at, the transaction date for a line after a transaction, else the filing's period of report; and the filing date beside it;
- the shares owned after the transaction, direct or indirect ownership and its nature, as filed;
- links by MDM id: the reporting owner (Person or Company, by CIK), the issuer Company (by CIK), and the Security once ticket 24 attaches the class title to it (empty until then).

**Blocked by:** security-mastering 01 (done). The Security link waits on [24](24-security-mastering-04-form-4-attaches-by-class.md); the rows land without it.

**Status:** closed: merged as PR #1134 (2026-10-22 15:33 ET)

- [x] `HOLDS` out of MDM's relationship types: `rules/merge/relationships.yaml` (relationship-types-v6), definitions and CONTEXT.md (Holdings is a silver row); the policy digest moves by one new layer, peeled back to the one before (`tests/mdm/policy_layers.py`); MDM, rules and fixture tests 1,072 passed (2026-10-22 14:44 ET)
- [x] The HOLDS line out of `rules/context/definitions.yaml` (a test holds the definitions equal to the types); #1121 edits another part of that file (operator, 2026-10-22: "Edit it now (Recommended)") (2026-10-22 15:23 ET)
- [x] Joint filers (operator, 2026-10-22: "Lines + owners, as SEC (Recommended)"): lines and owners apart, joined by accession, as SEC's Insider Transactions Data Sets keep them; 41 of the cohort's 3,367 filings are joint, 145 of its 11,451 lines (2026-10-22 16:23 ET)
- [x] The silver table specs: `silver-line.yaml` (`ownership_line`: the four line tables in one, key accession, table, line; `as_of`, `filed`; the issuer's MDM id; a flag check on D or I) and `silver-owner.yaml` (`ownership_owner`: key accession, owner CIK; the owner's Person by its record key, else its Company by CIK; the issuer's MDM id); both pass the writer's check (2026-10-22 16:23 ET)
- [x] The readings (bare XML and SGML, held equal by a test): each line gains `line_table`, `issuer_cik`, `as_of` (the transaction date, else the period of report) and `filed` (the SGML header's FILED AS OF DATE; the caller's for bare XML, else none); each owner gains `owner_record_key`, exactly the key MDM stores (tested against `adapters.record_key`). On the 3,367 local filings: all read, every line with an as-of date and a 10-digit issuer CIK, every amount a number, no key repeated (2026-10-22 16:23 ET)
- [x] Links by MDM id: the issuer by CIK, the owner as its Person or its Company (2026-10-22 16:23 ET)
- [ ] ~~The Security link~~ deferred to [24](24-security-mastering-04-form-4-attaches-by-class.md): a Form 4 names its class in words, never a CUSIP
- [x] Rows land in a disposable PostgreSQL 16 (`silver register`, `silver land`): a joint filing's lines land once with the issuer's MDM id and both dates, the person owner finds its Person and the fund its Company, a second delivery changes nothing (`tests/integration/test_ownership_silver.py`); with the reading, rules, catalog and MDM tests, 374 passed (2026-10-22 16:23 ET)
- [ ] ~~Scheduled landing by a Bookkeeping step~~ deferred to ticket 79's same gap: no Bookkeeping step lands silver yet (waits for #1121); `edgar-warehouse silver land` lands the rows by hand
- [x] A person's holding never makes the Person an issuer: holdings never reach MDM, and `ISSUED_BY` starts only at a Security (`rules/merge/relationships.yaml`; the type check refuses another kind, `tests/mdm/test_clean_relationship_types.py`) (2026-10-22 16:23 ET)
- [x] HOLDS out of MDM merged: PR #1134, CI green (2026-10-22 15:33 ET)
- [x] PR merged (the Form 4 silver holdings): #1134, CI green (2026-10-22 15:33 ET)
- [x] Learning → skill: `skills/data-onboarding/SKILL.md`, Relationships: only a link that describes the entities is an MDM relationship (14:44 ET); Silver target: a master with a several-part record key is found by the key as MDM writes it (a compact JSON list), built in the reading and tested against `adapters.record_key`; rows several parties share keep the source's own shape, lines once and parties apart (2026-10-22 16:23 ET)
