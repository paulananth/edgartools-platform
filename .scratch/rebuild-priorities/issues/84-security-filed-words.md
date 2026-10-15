# A Security's issuer name and class title: which filed words it keeps

Priority: 84, tier 2. Map: [Rebuild priorities](../map.md).

Type: grilling, then task. Status: open. Blocked by: 79 (Onboard funds and securities with the skills: the Security master these words sit on).

## Why

Found onboarding the 13F information tables (ticket 79). The operator ruled "A" (2026-10-14): the Security carries the issuer name and class title as filed. The filers do not agree on them:

- 999 local files, 31,071 CUSIPs as filed: 83,785 CUSIP and name pairs, 89,557 CUSIP and title pairs. A CUSIP is filed with about three names and three titles on average.
- Profiling counts 381,219 of 2,953,581 holding rows (13%) whose class title differs from the most common title of their CUSIP (`carried_value_disagrees`, titleOfClass), and 28,772 that differ from the most common one of their FIGI.
- The information tables carry no filing date, so the reduction keeps the **lexically first** name and title of each CUSIP (`reduce.yaml`, `sample_limit: 1`), not the most common one profiling compares against. The two choices differ.
- No record-level data quality check can catch this: each Security record holds one name and one title after the reduction, so the disagreement is between holding rows, not within a record. The data-quality helper drafts 0 checks for the part (ticket 79's quality step).

## Question

Which name and title does a Security keep when its filers disagree, and is a filed word ever normalised (for example an abbreviation of a class such as common stock written several ways)?

Options to put to the operator, one at a time:
1. Keep the most common filed word per CUSIP (needs a reduction mode that keeps the member with the largest count; a source-engine change, for a code ticket).
2. Keep the lexically first (today: deterministic, no engine change, but arbitrary).
3. Take the name and title from a better source once onboarded: N-PORT's issuer name and LEI (ticket 79's N-PORT parts), or OpenFIGI's name and security description (ticket 80), ranked first in `rules/merge/kinds/security.yaml`.
4. A code set for class titles in RDM (normalised titles with synonyms), with the filed title kept beside it.

## Checklist

- [ ] The operator's ruling on which filed word a Security keeps
- [ ] If a reduction mode is needed: its own code ticket, written first, coded only on the operator's word
- [ ] The 13F configuration changed to the ruling; tested on the 999 local files; counts compared with today's (20,311 Securities)
- [ ] Every skill gap found on the way: fixed in the skill, on its own branch
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
