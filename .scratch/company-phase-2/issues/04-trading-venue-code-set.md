# Trading Venue: cover wording to MIC

Status: open
Type: task
Owner: claude (map decisions 12, 13)
Blocked by: 01

An RDM code set maps each exchange wording a registration or prospectus cover gives to its ISO 10383 MIC (RDM's
`iso-10383-mic`). A ticker several Securities hold resolves to the one listed at that operating MIC, then by the `US` ISIN; a
wording the set lacks is Set Aside as "exchange not mapped".

## Checklist

- [ ] The code set (12 wordings today), reviewed row by row, published and pinned
- [ ] The listing's operating MIC readable by Gold from the mirrored master
- [ ] Tests: one ticker per venue, a shared ticker, an unmapped wording
- [ ] `/code-review`
- [ ] Learning → skill
