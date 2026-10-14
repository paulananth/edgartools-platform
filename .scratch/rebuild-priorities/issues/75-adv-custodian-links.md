# Form ADV custodian links into MDM

Priority: 75, tier 3, product value (numbered after the map was charted). Map: [Rebuild priorities](../map.md).

Status: open
Blocked by: 74 (the Merge Stage has no limit)

## Why

Form ADV's custodian links were kept out of MDM only because of the Merge Stage's 10,000-record closure cap, which ticket 74 removes. Operator, 2026-10-14 08:19 ET: "Yes, a new ticket (Recommended)".

## Checklist

- [ ] Find where the custodian links were left out, and why (the onboarding log of `iapd.adv`)
- [ ] The link types: the source's own term, each from `rules/merge/relationships.yaml` or approved by its name
- [ ] Measure on the local copies (counts only), with the faster Merge Stage
- [ ] The ADV matching rules' own switch-on (ticket 76)
- [ ] PR, CI green, merge on the operator's word
