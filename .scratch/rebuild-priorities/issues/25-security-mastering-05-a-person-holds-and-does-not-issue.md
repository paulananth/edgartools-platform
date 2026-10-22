# 05: A Person's Form 4 holdings land in silver

Priority: 25, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/05-a-person-holds-and-does-not-issue.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**Re-scoped (operator, 2026-10-22: "Agreed Remove HOLDS from MDM's relationship types", "Re-scope ticket 25 to land Form 4 holdings in silver"):** a holding is a position restated every filing with its amount, so it is a silver row carrying the MDM ids of the holder and the Security, never a relationship MDM masters. `HOLDS` is no longer an MDM relationship type (relationship-types-v6). The Person is never the issuer: `ISSUED_BY` still points at the Company or the Fund Company.

**What to build:** a silver table of Forms 3/4/5 holdings: one row per holding line (non-derivative and derivative, transaction and holding tables), as filed, with:
- **its as-of date**: the date the position holds at, the transaction date for a line after a transaction, else the filing's period of report; and the filing date beside it;
- the shares owned after the transaction, direct or indirect ownership and its nature, as filed;
- links by MDM id: the reporting owner (Person or Company, by CIK), the issuer Company (by CIK), and the Security once ticket 24 attaches the class title to it (empty until then).

**Blocked by:** security-mastering 01 (done). The Security link waits on [24](24-security-mastering-04-form-4-attaches-by-class.md); the rows land without it.

**Status:** ready-for-agent

- [x] `HOLDS` out of MDM's relationship types: `rules/merge/relationships.yaml` (relationship-types-v6) and CONTEXT.md (Holdings is a silver row); the policy digest moves by one new layer, peeled back to the one before (`tests/mdm/policy_layers.py`); MDM, rules and fixture tests 1,072 passed (2026-10-22 14:44 ET)
- [ ] ~~The unused HOLDS line in `rules/context/definitions.yaml` removed~~ deferred to [132](132-relationship-types-in-one-place.md): Codex's PR #1121 edits that file; an unused line breaks nothing (definition tests 61 passed)
- [ ] The silver table spec for Forms 3/4/5 holdings, with its as-of date
- [ ] The reading tables give each line its as-of date and filing date
- [ ] Links by MDM id: owner and issuer by CIK; the Security once 24 attaches it
- [ ] Rows land in a disposable PostgreSQL 16 (`silver register`, `silver land`), test
- [ ] A person's holding never makes the Person an issuer (no `ISSUED_BY` from a Person), test
- [ ] PR merged
- [ ] Learning → skill (part done: `skills/data-onboarding/SKILL.md`, Relationships: only a link that describes the entities is an MDM relationship; a position or event is a silver row with both MDM ids and its as-of date, 2026-10-22 14:44 ET)
