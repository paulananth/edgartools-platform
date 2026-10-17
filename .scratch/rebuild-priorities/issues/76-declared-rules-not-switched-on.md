# Matching rules declared but not switched on

Priority: 76, tier 3, product value (numbered after the map was charted). Map: [Rebuild priorities](../map.md).

Status: in review (#1042)
Blocked by: none

## Why

These rules are in `rules/merge/kinds/company.yaml`, but they are not in the Mastering Policy's switched-on rules (`rules/merge/policy.yaml`), and nothing on the map tracked them. Operator, 2026-10-14 08:19 ET: "Track them on the map (Recommended)": for each family, measure it, then ask the operator to switch it on or delete it.

## Checklist

- [ ] ~~GLEIF cascade `sec-gleif-cascade-p1` to `p7`~~ already tracked by ticket 09 ("Cascade name-and-address passes: label and switch on"), found 2026-10-14 12:50 ET; this ticket keeps the Form ADV rules
- [x] Form ADV `iapd-adv-crd`, `iapd-adv-custodian-lei` and `iapd-adv-custodian-bd` (2026-10-09.1): the same. Switched on: `rules/merge/policy.yaml` `automatic_rules`, and the `crd`, `lei` and `bd_number` Identifier Contracts verified on the run below (`corpus_sha256` of `research/76-adv-merge-run.json`). New policy layer `without_adv_switch_on` (Company digest `a5e9b113…`; peeled, `bd71d9ad…` as before); the integration answer file's whole-policy digest moves to `eb02bb0f…`; three tests no longer switch the rules on themselves. 912 MDM and rules tests and 39 integration tests pass, `mapdoc check` clean (2026-10-17 08:39 ET)
- [x] Each answer recorded here with the operator's words and the ET time: ADV rules, "Switch on all three (Recommended)", 2026-10-17 08:31 ET
- [x] Re-run the ADV rules' proof before switch-on: since ticket 97 GLEIF is an LEI source, so a custodian LEI already held by a GLEIF-bound Company joins it instead of creating one, and an LEI on two Companies goes to review (noted 2026-10-16 13:16 ET): all 13 ADV months, GLEIF Level 1 (28,890 records: the 28,397 N-PORT issuer LEIs and the pinned SEC cohort's) and the SEC Companies, through the Merge Stage on PostgreSQL 16 with `iapd-adv-crd`, `iapd-adv-custodian-lei` and `iapd-adv-custodian-bd` switched on in the run's own policy only (`research/76-adv-merge-run.json`, 22 min, three passes, the third changed nothing). 24,760 Companies: 17,646 advisers (none joins an SEC or GLEIF Company: the adviser's LEI is lookup only by the 2026-10-09 ruling, and SEC records carry no CRD), 724 custodians (2,906 of the 6,717 custodian records bound by BD number or LEI; 24 joined an SEC Company with its GLEIF record, and 97 more took their GLEIF record), 6,414 SEC Companies (3,052 with their GLEIF record, 24 of them also custodians). 0 LEIs, 0 CRD numbers and 0 BD numbers on two Companies, so no duplicate by identifier. Waiting: 3,811 custodian records named only by name, 21,442 GLEIF records with no Company of their LEI (wait, by design), and the set-asides as before (76 custodian LEI check digit, 312 SEC classification, 4,299 GLEIF identity kind) (2026-10-17 08:29 ET)
- [x] Ask the operator to switch on the three ADV rules, with this evidence: asked and answered 2026-10-17 08:31 ET
- [x] Learning → skill: the line in ticket 75 (`skills/mdm-engineering/SKILL.md`, a waiting record needs a later pass) (2026-10-17 08:39 ET)
- [ ] PR #1042, CI green, merge on the operator's word
