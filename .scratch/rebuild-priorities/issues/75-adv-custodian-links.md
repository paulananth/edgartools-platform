# Form ADV custodian links into MDM

Priority: 75, tier 3, product value (numbered after the map was charted). Map: [Rebuild priorities](../map.md).

Status: in review (PR open, 2026-10-16)
Blocked by: none (74 merged as #960)

## Why

Form ADV's custodian links were kept out of MDM only because of the Merge Stage's 10,000-record closure cap, which ticket 74 removes. Operator, 2026-10-14 08:19 ET: "Yes, a new ticket (Recommended)".

## Checklist

- [x] Find where the custodian links were left out, and why (the onboarding log of `iapd.adv`): profiling ticket 07 (rebuild-priorities 01), 2026-10-09 14:44-14:56 ET: the Merge Stage refused a connected group over 10,000 records (one custodian named in 17,333 custody rows); the operator then ruled one custodian record per monthly file and the history read from silver, so CUSTODIAN left the types; the full 13-month run had 0 links (2026-10-16 19:05 ET)
- [x] The link types: the source's own term, each from `rules/merge/relationships.yaml` or approved by its name: `CUSTODIAN`, the name the operator approved 2026-10-09 10:38 ET ("CUSTODIAN (Recommended)"), back in the types (relationship-types-v4) and the context definitions; configuration only: `combine.yaml` collects each filing's distinct custodian ids, the filings contract links its adviser to the custodians contract's record of each in the same monthly file. `tests/integration/test_adv_custodian_link.py`: two invented months through the real chain and the Merge Stage: BD-number and LEI custodians linked, a name-only one waits, a custodian named again keeps one link (start the first month, `last_seen` the later one); fails with the month left out of the target. Policy layer `without_custodian` peels back to the digest before; 812 MDM and rules tests pass (2026-10-16 19:20 ET)
- [x] Measure on the local copies (counts only): all 13 months through the configured chain without MDM (`research/75_custodian_link_counts.py`, 34 s; report `research/75-custodian-link-counts.json`): 46,640 filings and 6,717 custodian records, as the full Proving Run's; 50,073 links stated: 37,094 to a custodian by BD number, 5,186 by LEI (these can resolve), 7,793 named only by name (wait for a name rule), 94 to a custodian record set aside (LEI check digit); 18,571 adviser-custodian links once folded, 11,860 named in more than one month; at most 15 on a filing (2026-10-16 19:27 ET)
- [ ] Resolved in MDM, with GLEIF and SEC Companies loaded beside them (duplicates, an LEI on two Companies, links resolved and waiting, the time per batch): one run, together with ticket 76's re-proof of the ADV rules
- [ ] The ADV matching rules' own switch-on (ticket 76)
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
