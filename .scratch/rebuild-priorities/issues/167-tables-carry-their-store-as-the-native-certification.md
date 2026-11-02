# 167: Tables carry their store as the native certification

Priority: 167. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 07:00 ET (operator, 2026-11-02: "classification is missing", "mdm, rdm, silver", then "map mdm, rdm, silver to native openmetadata classification" and "rdm = Gold, MDM = Gold, Silver=Silver").

Type: task. Status: open (live publish waits for ticket 168). Blocked by: none.

## Question

Which native classification marks the store of a table (mdm, rdm, silver)?

Answer: the native Certification. mdm Gold, rdm Gold, silver Silver. A source dataset carries none. A first version wrote a custom `processing_layer` classification; the operator asked for the native one and it was dropped before merge.

## Parts

- [x] GoF consult: leave `_data_classes`; certification already has its code, only the rdm store is added (2026-11-02 07:00 ET)
- [x] The plan certifies mdm and rdm Gold, silver Silver, sources none (`test_master_and_reference_tables_are_gold_and_silver_tables_are_silver`, 2026-11-02 07:00 ET)
- [x] `check` reports a table with a missing class tag or certification (`test_check_says_when_a_table_is_not_certified_as_planned`, 38 pass, 2026-11-02 07:00 ET)
- [ ] Live: delete the custom `processing_layer` classification, publish, `check` matches, read certification back (waits for ticket 168 so the publish does not force Draft)
- [x] Learning → skill: `skills/openmetadata/SKILL.md`, data-catalog and data-onboarding say rdm is Gold and the layer is the certification
