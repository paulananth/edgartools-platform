# 129: Fields in MDM that belong elsewhere (review of 2026-10-22)

Priority: 129. Map: [Rebuild priorities](../map.md). Raised by the operator's
review request, 2026-10-22: "Review using onboarding skill are there fields that
must be silver incorrectly in mdm"; rulings: "Fix 1, 2 date that changes usually
should not be in MDM unless it adds meaning to the entity or turn on or off".

Type: task. Status: in progress; fix 2 waits for Codex's PR #1121 (operator, 2026-10-22: "Wait for #1121 (Recommended)"). Blocked by: #1121 (fix 2 only).

## What the review found

Every MDM field the 14 Dataset Contracts fill, checked against the
data-onboarding skill's map rules:

1. `issuer_lei` on the N-PORT Security: an LEI identifies a Company ("A value
   of another kind stays out of this kind"); the Security reaches its issuer by
   ISSUED_BY (ticket 22). The filed LEI is evidence of the holding.
2. `gleif_last_update` and `gleif_next_renewal` on the Company: GLEIF's
   record-keeping dates; they change at each renewal and give the Company a new
   version without a change in the entity. GLEIF's record already carries
   LastUpdateDate as its effective time.
3. `sic_description` on the Company: a code's label, which belongs in an RDM
   SIC code set (the Company keeps `sic`).
4. `share_class_figi` on the OpenFIGI Security: a field and a cross-reference
   both; the cross-reference alone is enough.
5. Not a field: the Form ADV custodian Dataset Contract keys its records on
   `[published, custodian_id]`, so each publication makes a new MDM record for
   the same custodian; the publication date belongs in the publication key.

Clean: no amounts, positions, transactions or quarter dates are in MDM.

## Checklist

- [x] Review of every Dataset Contract's MDM fields (2026-10-22 11:27 ET)
- [x] Fix 1: `issuer_lei` out of the Security's Dataset Contract; the filed LEI is a column of the silver holding row (`silver-holding.yaml`); MAPPING.xlsx and security.xlsx regenerated; tests: N-PORT, OpenFIGI and rules 77 passed, MDM folder 896 passed (2026-10-22 11:27 ET)
- [ ] Fix 2: `gleif_last_update` and `gleif_next_renewal` out of the Company: a migration that drops the two Company columns and the field writer's use of them; the census contracts' copies; the cascade and census matching check freshness against the GLEIF record's effective time (`cascade.py:138`, `matching.py:117,142`), not the field. `matching.py` is in Codex's open PR #1121, which also adds MDM migration 024; built right after #1121 merges, on its numbering (operator, 2026-10-22: "Wait for #1121 (Recommended)")
- [ ] ~~3: `sic_description` to an RDM SIC code set~~ deferred: its own onboarding (a code set)
- [ ] ~~4: `share_class_figi` field~~ deferred: a merge-policy change with a new fingerprint
- [ ] ~~5: the custodian record key~~ deferred: a Dataset Contract record-key change, with its own test
- [x] Learning → skill: `skills/data-onboarding/SKILL.md`, map "Fields": a date that usually changes stays out of MDM unless it adds meaning or switches the entity on or off; evidence about a link stays on the silver row. `skills/refining-rules/SKILL.md`: which target a field belongs to (name every engine reader before moving one), and a field change regenerates both the source and the kind workbook (2026-10-22 11:27 ET)
