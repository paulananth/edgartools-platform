# Gold links: by identifier, several kinds, Set Aside out of scope

Status: open
Type: task
Owner: claude (map decisions 7, 9, 10)
Blocked by: 02, 04

A link resolves by its identifier on any master of its kinds; a link may name several kinds; its test counts only rows whose
key the Set Aside table does not hold, and every one resolves to exactly one master. The reporting owner's two links become one,
`[person, company]` by CIK.

## Checklist

- [ ] GoF consult on `edgar_warehouse/gold/views.py`
- [ ] Silver specs: `kinds` lists where an issuer or owner may be either
- [ ] Views and tests generated; a test per kind of link fails on today's generator
- [ ] A Security's listing operating MIC readable by Gold from the mirrored master (from ticket 04)
- [ ] A registration or prospectus ticker several Securities hold resolves by its cover's Trading Venue (`ref_sec_cover_exchange` to `ref_iso_10383_mic`'s operating MIC), then the `US` ISIN; a row whose wording `sec-cover-exchange` lacks, or which gives none, is out of the link test as "exchange not mapped" (from ticket 04)
- [ ] `/code-review`
- [ ] Learning → skill
