# Trading Venue: cover wording to MIC

Status: open
Type: task
Owner: claude (map decisions 12, 13)
Blocked by: 01

An RDM code set maps each exchange wording a registration or prospectus cover gives to its ISO 10383 MIC (RDM's
`iso-10383-mic`). A ticker several Securities hold resolves to the one listed at that operating MIC, then by the `US` ISIN; a
wording the set lacks is Set Aside as "exchange not mapped".

## Checklist

- [x] The code set `sec-cover-exchange` version 1: the 12 wordings on the hosted covers are 8 once upper-cased and trimmed, each crosswalked to its ISO 10383 MIC (`iso-10383-mic` version 1); reviewed row by row and approved (operator, "yes", recorded 2026-11-27 22:19 ET); published to `rules/reference/published/sec-cover-exchange/1` (sha256 equals its pin); `scripts/dev/reload_rdm.py` reloads it into a fresh RDM (12 versions, each equal to its pin); Gold reads it as `ref_sec_cover_exchange` (2026-11-27 22:19 ET)
- [ ] ~~The listing's operating MIC readable by Gold from the mirrored master~~ deferred to ticket 06: Gold exposes no Security listing today, and the ticker resolution that reads it is 06's
- [x] Tests: each wording names its venue (a segment through ISO's parent to its operating MIC), case and spacing ignored, and an unmapped wording names none (`tests/unit/test_sec_cover_exchange.py`, 1 passed; the pin is checked by `scripts/dev/reload_rdm.py`; Gold, RDM and exposure unit tests 350 passed) (2026-11-27 22:19 ET)
- [ ] ~~A shared ticker resolves among its Securities by venue, then the `US` ISIN~~ deferred to ticket 06, which builds that resolution
- [ ] ~~A registration or prospectus row whose wording the set lacks (or which gives none) is Set Aside as "exchange not mapped"~~ deferred to ticket 06: the code set names no venue for it (tested); excluding the row from the link test is 06's resolution
- [x] `/code-review`, three axes on `reviewer`. GoF: leave it. Spec: the mappings are right; the "exchange not mapped" Set Aside was neither built nor deferred, now deferred to and listed on ticket 06. Standards: the test that hashed the published file and the skill row's ticket number are gone, and the test states what it guarantees. Left: the test reads the code set's rows itself, since nothing reads them in production until ticket 06 (2026-11-27 22:19 ET)
- [x] Learning → skill: `skills/security-master/SKILL.md`, RDM code sets: `sec-cover-exchange` and its source (2026-11-27 22:19 ET)
